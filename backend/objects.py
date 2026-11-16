"""Selected-image crops and one explicit Tripo image-to-3D task; no simulated geometry."""
import hashlib
import io
import json
import math
import struct
import time
from urllib.parse import quote, urlparse

import httpx
from PIL import Image

from . import store
from .config import tripo_config

BASE_URL = "https://openapi.tripo3d.ai/v3"
UPLOAD_ENDPOINT = BASE_URL + "/files"
GENERATION_ENDPOINT = BASE_URL + "/generation/image-to-model"
MAX_MODEL_BYTES = 64 * 1024 * 1024
MAX_TASK_SECONDS = 300


def crop_subject(project_id, selection):
    bounds = [selection.get(key) for key in ("x", "y", "width", "height")]
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in bounds):
        raise ValueError("Choose a valid subject selection.")
    x, y, width, height = bounds
    if min(x, y) < 0 or min(width, height) <= 0 or x + width > 1.000001 or y + height > 1.000001:
        raise ValueError("Keep the subject selection inside the photograph.")
    with Image.open(store.project_dir(project_id) / "image.jpg") as image:
        left, top = round(x * image.width), round(y * image.height)
        right, bottom = min(image.width, round((x + width) * image.width)), min(image.height, round((y + height) * image.height))
        if right - left < 32 or bottom - top < 32:
            raise ValueError("Select a subject at least 32 pixels wide and high.")
        cropped = image.crop((left, top, right, bottom)).convert("RGB")
        cropped.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        cropped.save(buffer, "JPEG", quality=94, exif=b"")
    return buffer.getvalue()


def validate_glb(data):
    if len(data) < 24 or len(data) > MAX_MODEL_BYTES:
        raise ValueError("The 3D model is empty or exceeds the 64 MB viewer limit.")
    magic, version, length, json_length, kind = struct.unpack_from("<4sIIII", data)
    if magic != b"glTF" or version != 2 or length != len(data) or kind != 0x4E4F534A or json_length > length - 20:
        raise ValueError("The service did not return a valid GLB 2.0 model.")
    try:
        document = json.loads(data[20:20 + json_length])
        if not isinstance(document, dict):
            raise ValueError("Invalid scene document")
        if not document.get("meshes") or not document.get("scenes"):
            raise ValueError("No scene geometry")
        for resource in document.get("buffers", []) + document.get("images", []):
            if "uri" in resource and not str(resource["uri"]).startswith("data:"):
                raise ValueError("External resource")
        unsupported = {"KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_texture_basisu"}
        if unsupported.intersection(document.get("extensionsRequired", [])):
            raise ValueError("Unsupported compression")
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError("The model must contain a self-contained scene with embedded resources and no required external compression decoder.") from exc
    return document


def checked_json(response, action):
    if not 200 <= response.status_code < 300:
        reasons = {
            401: "Tripo rejected the API key. Check TRIPO_API_KEY privately.",
            402: "Tripo API credits are required. Check your Tripo account.",
            403: "Your Tripo account cannot access this model or API.",
            429: "Tripo rate or credit limit reached. Check your account before retrying.",
        }
        raise ValueError(reasons.get(response.status_code, f"Tripo {action} failed (HTTP {response.status_code}). Check the provider dashboard before retrying."))
    try:
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
            if isinstance(payload, dict) and payload.get("code") == 1007:
                raise ValueError("Tripo rate limit reached. Wait before retrying and check the provider dashboard.")
            raise ValueError(f"Tripo {action} was rejected. Check the provider dashboard before retrying.")
        return payload["data"]
    except (ValueError, TypeError) as exc:
        if str(exc).startswith("Tripo "):
            raise
        raise ValueError("Tripo returned an invalid response. Check its dashboard before retrying.") from exc


def download_model(client, url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "cdn.tripo3d.ai" or parsed.username or parsed.port not in (None, 443):
        raise ValueError("Tripo returned an unsupported model download address.")
    # No Authorization header is sent to the asset CDN; download URLs remain backend-only.
    with client.stream("GET", url, follow_redirects=False) as response:
        if response.status_code != 200:
            raise ValueError("The model download failed. Resume this existing task to fetch it again.")
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > MAX_MODEL_BYTES:
                raise ValueError("The 3D model exceeds the 64 MB viewer limit.")
    validate_glb(bytes(data))
    return bytes(data)


def run(job, send, client=None, poll_interval=2):
    completed_folder = store.project_dir(job["project_id"]) / "object" / job["id"]
    if (completed_folder / "manifest.json").exists() and not store.cancel_requested(job["id"]):
        validate_glb((completed_folder / "model.glb").read_bytes())
        return json.loads((completed_folder / "manifest.json").read_text(encoding="utf-8"))
    config = tripo_config()
    if not config["api_key"]:
        raise ValueError("Add TRIPO_API_KEY to your private local .env file for Object 360 generation.")
    parameters = job["parameters"]
    if not parameters.get("allow_external_processing"):
        raise ValueError("Allow sending the selected crop to Tripo before generating.")
    if isinstance(parameters.get("model"), str) and parameters["model"].startswith("meshy-"):
        raise ValueError("This saved task belongs to the previous image-to-3D provider and cannot be resumed by Tripo.")
    if parameters.get("model") != config["model"]:
        raise ValueError("This saved job uses another image-to-3D model. Start a new Tripo generation.")
    if store.cancel_requested(job["id"]):
        raise ValueError("Object generation cancelled before sending the selected crop.")
    source = crop_subject(job["project_id"], parameters["selection"])
    headers = {"Authorization": "Bearer " + config["api_key"]}
    task_id = job.get("remote_id")
    owns_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(60, connect=15), trust_env=False)
    started = time.monotonic()
    try:
        if not task_id:
            send({"stage": "Uploading selected subject to Tripo", "progress": 8})
            response = checked_json(
                client.post(UPLOAD_ENDPOINT, headers=headers, files={"file": ("subject.jpg", source, "image/jpeg")}),
                "image upload",
            )
            file_token = response.get("file_token")
            if not isinstance(file_token, str) or not file_token or len(file_token) > 256:
                raise ValueError("Tripo did not return a file token. Check its dashboard before starting another generation.")
            if store.cancel_requested(job["id"]):
                raise ValueError("Object generation cancelled before the Tripo generation task was submitted.")
            send({"stage": "Submitting Tripo image-to-3D task", "progress": 12})
            payload = {
                "input": file_token,
                "model": config["model"],
                "texture": True,
                "pbr": True,
                "face_limit": 50000,
            }
            if parameters.get("orientation") == "align_image":
                payload["orientation"] = "align_image"
            # Submit exactly once. Persist the task ID immediately for reconnect/resume.
            response = checked_json(client.post(GENERATION_ENDPOINT, headers=headers, json=payload), "generation submission")
            task_id = response.get("task_id")
            if not isinstance(task_id, str) or not task_id or task_id in (".", "..") or len(task_id) > 200:
                raise ValueError("Tripo did not return a task ID. Check its dashboard before starting another generation.")
            store.update_job(job["id"], remote_id=task_id)
        task_url = BASE_URL + "/tasks/" + quote(task_id, safe="")
        task_started = time.monotonic()
        while True:
            if store.cancel_requested(job["id"]):
                raise ValueError("Generation was cancelled locally. Tripo may continue the saved task and charge credits if it succeeds; check the Tripo dashboard.")
            if time.monotonic() - task_started >= MAX_TASK_SECONDS:
                raise ValueError("Tripo is still processing after five minutes. The task ID is saved; resume this task later instead of starting another generation.")
            task = checked_json(client.get(task_url, headers=headers), "status check")
            status = task.get("status")
            if status == "success":
                break
            if status in ("failed", "cancelled", "banned", "expired"):
                raise ValueError("Tripo could not complete this model. Inspect the task in your provider dashboard.")
            progress = task.get("progress", 0)
            progress = max(12, min(88, int(progress) * 0.76 + 12)) if isinstance(progress, (int, float)) and math.isfinite(progress) else 12
            send({"stage": "Tripo is reconstructing the selected subject", "progress": round(progress)})
            until = time.monotonic() + poll_interval
            while time.monotonic() < until and not store.cancel_requested(job["id"]):
                time.sleep(min(0.2, until - time.monotonic()))
        if store.cancel_requested(job["id"]):
            raise ValueError("Object generation cancelled before download.")
        send({"stage": "Downloading and validating the 3D model", "progress": 92})
        output = task.get("output")
        url = output.get("model_url") if isinstance(output, dict) else None
        if not isinstance(url, str):
            raise ValueError("Tripo finished without a GLB model. Inspect the task in its dashboard.")
        data = download_model(client, url)
        if store.cancel_requested(job["id"]):
            raise ValueError("Object generation cancelled before saving.")
        folder = store.project_dir(job["project_id"]) / "object"
        temporary, target = folder / (job["id"] + ".tmp"), folder / job["id"]
        temporary.mkdir(parents=True, exist_ok=True)
        (temporary / "model.glb").write_bytes(data)
        (temporary / "subject.jpg").write_bytes(source)
        result = {
            "job_id": job["id"],
            "provider": "tripo",
            "model": parameters.get("model", config["model"]),
            "orientation": parameters.get("orientation", "default"),
            "remote_id": task_id,
            "ai_generated": True,
            "selection": parameters["selection"],
            "source_sha256": hashlib.sha256(source).hexdigest(),
            "model_sha256": hashlib.sha256(data).hexdigest(),
            "model_bytes": len(data),
            "processing_seconds": round(time.monotonic() - started, 3),
            "consumed_credits": task.get("credits_consumed"),
            "warning": "Single-photo reconstruction infers hidden surfaces. Face, hair, hands, pose and the unseen back can differ from the real person.",
            "assets": {kind: f"/api/projects/{job['project_id']}/files/{kind}?job_id={job['id']}" for kind in ("object_model", "object_input", "object_manifest")},
        }
        (temporary / "manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        temporary.rename(target)
        return result
    except httpx.RequestError as exc:
        raise ValueError("Tripo disconnected or timed out. It may still be processing and using credits. Resume the saved task if available; no automatic generation retry was made.") from exc
    finally:
        if owns_client:
            client.close()
