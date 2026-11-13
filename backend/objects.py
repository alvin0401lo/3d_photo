"""Selected-image crops and one explicit Meshy image-to-3D task; no simulated geometry."""
import base64
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
from .config import meshy_config

ENDPOINT = "https://api.meshy.ai/openapi/v1/image-to-3d"
MAX_MODEL_BYTES = 64 * 1024 * 1024


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
    magic, version, length, json_length, kind = struct.unpack_from('<4sIIII', data)
    if magic != b'glTF' or version != 2 or length != len(data) or kind != 0x4E4F534A or json_length > length - 20:
        raise ValueError("The service did not return a valid GLB 2.0 model.")
    try:
        document = json.loads(data[20:20 + json_length])
        if not isinstance(document, dict): raise ValueError('Invalid scene document')
        if not document.get('meshes') or not document.get('scenes'):
            raise ValueError('No scene geometry')
        for resource in document.get('buffers', []) + document.get('images', []):
            if 'uri' in resource and not str(resource['uri']).startswith('data:'):
                raise ValueError('External resource')
        unsupported = {'KHR_draco_mesh_compression', 'EXT_meshopt_compression', 'KHR_texture_basisu'}
        if unsupported.intersection(document.get('extensionsRequired', [])):
            raise ValueError('Unsupported compression')
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError("The model must contain a self-contained scene with embedded resources and no required external compression decoder.") from exc
    return document


def checked_json(response, action):
    if not 200 <= response.status_code < 300:
        reasons = {401: "Meshy rejected the API key. Check MESHY_API_KEY privately.", 402: "Meshy API credits are required. Check your Meshy account.", 403: "Your Meshy account cannot access this model or API.", 429: "Meshy rate or credit limit reached. Check your account before retrying."}
        raise ValueError(reasons.get(response.status_code, f"Meshy {action} failed (HTTP {response.status_code}). Check the provider dashboard before retrying."))
    try:
        payload = response.json()
        if not isinstance(payload, dict): raise ValueError('Invalid object')
        return payload
    except (ValueError, TypeError) as exc:
        raise ValueError("Meshy returned an invalid response. Check its dashboard before retrying.") from exc


def download_model(client, url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'assets.meshy.ai' or parsed.username or parsed.port not in (None, 443):
        raise ValueError("Meshy returned an unsupported model download address.")
    # No Authorization header is sent to the asset CDN; signed URLs remain backend-only.
    with client.stream('GET', url, follow_redirects=False) as response:
        if response.status_code != 200:
            raise ValueError("The model download failed. Resume this existing task to fetch it again.")
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > MAX_MODEL_BYTES:
                raise ValueError("The 3D model exceeds the 64 MB viewer limit.")
    validate_glb(bytes(data))
    return bytes(data)


def run(job, send, client=None, poll_interval=5):
    completed_folder = store.project_dir(job['project_id']) / 'object' / job['id']
    if (completed_folder / 'manifest.json').exists() and not store.cancel_requested(job['id']):
        validate_glb((completed_folder / 'model.glb').read_bytes())
        return json.loads((completed_folder / 'manifest.json').read_text(encoding='utf-8'))
    config = meshy_config()
    if not config['api_key']:
        raise ValueError("Add MESHY_API_KEY to your private local .env file for Object 360 generation.")
    parameters = job['parameters']
    if not parameters.get('allow_external_processing'):
        raise ValueError("Allow sending the selected crop to Meshy before generating.")
    if store.cancel_requested(job['id']):
        raise ValueError("Object generation cancelled before sending the selected crop.")
    source = crop_subject(job['project_id'], parameters['selection'])
    headers = {'Authorization': 'Bearer ' + config['api_key']}
    task_id = job.get('remote_id')
    owns_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(60, connect=15), trust_env=False)
    started = time.monotonic()
    try:
        if not task_id:
            send({'stage': 'Sending selected subject to Meshy', 'progress': 8})
            payload = {'image_url': 'data:image/jpeg;base64,' + base64.b64encode(source).decode(), 'ai_model': parameters.get('model', config['model']), 'should_texture': True, 'should_remesh': True, 'target_polycount': 30000, 'target_formats': ['glb']}
            if parameters.get('pose') in ('a-pose', 't-pose'):
                payload['pose_mode'] = parameters['pose']
            # POST exactly once. Reconnection uses the stored task ID, never another paid task.
            response = checked_json(client.post(ENDPOINT, headers=headers, json=payload), 'submission')
            task_id = response.get('result')
            if not isinstance(task_id, str) or not task_id or task_id in ('.', '..') or len(task_id) > 200:
                raise ValueError("Meshy did not return a task ID. Check its dashboard before starting another generation.")
            store.update_job(job['id'], remote_id=task_id)
        task_url = ENDPOINT + '/' + quote(task_id, safe='')
        while True:
            if store.cancel_requested(job['id']):
                try: client.delete(task_url, headers=headers)
                except httpx.RequestError: pass
                raise ValueError("Object generation cancelled locally. Meshy may already have used credits; inspect its dashboard.")
            task = checked_json(client.get(task_url, headers=headers), 'status check')
            status = task.get('status')
            if status == 'SUCCEEDED': break
            if status in ('FAILED', 'CANCELED'):
                raise ValueError("Meshy could not complete this model. Inspect the task in your provider dashboard.")
            if status not in ('PENDING', 'IN_PROGRESS'):
                raise ValueError("Meshy returned an unknown task state. Resume this existing task after checking its dashboard.")
            progress = task.get('progress', 0)
            progress = max(10, min(88, int(progress) * .8 + 10)) if isinstance(progress, (int, float)) and math.isfinite(progress) else 10
            send({'stage': 'Meshy is reconstructing the selected subject', 'progress': round(progress)})
            until = time.monotonic() + poll_interval
            while time.monotonic() < until and not store.cancel_requested(job['id']): time.sleep(.2)
        if store.cancel_requested(job['id']): raise ValueError('Object generation cancelled before download.')
        send({'stage': 'Downloading and validating the 3D model', 'progress': 92})
        url = task.get('model_urls', {}).get('glb')
        if not isinstance(url, str): raise ValueError('Meshy finished without a GLB model. Inspect the task in its dashboard.')
        data = download_model(client, url)
        if store.cancel_requested(job['id']): raise ValueError('Object generation cancelled before saving.')
        folder = store.project_dir(job['project_id']) / 'object'
        temporary, target = folder / (job['id'] + '.tmp'), folder / job['id']
        temporary.mkdir(parents=True, exist_ok=True)
        (temporary / 'model.glb').write_bytes(data)
        (temporary / 'subject.jpg').write_bytes(source)
        result = {'job_id': job['id'], 'provider': 'meshy', 'model': parameters.get('model', config['model']), 'remote_id': task_id, 'ai_generated': True, 'selection': parameters['selection'], 'source_sha256': hashlib.sha256(source).hexdigest(), 'model_sha256': hashlib.sha256(data).hexdigest(), 'model_bytes': len(data), 'processing_seconds': round(time.monotonic() - started, 3), 'consumed_credits': task.get('consumed_credits'), 'warning': 'Single-photo reconstruction infers hidden surfaces. Face, hair, hands, pose and the unseen back can differ from the real person.', 'assets': {kind: f"/api/projects/{job['project_id']}/files/{kind}?job_id={job['id']}" for kind in ('object_model', 'object_input', 'object_manifest')}}
        (temporary / 'manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        temporary.rename(target)
        return result
    except httpx.RequestError as exc:
        raise ValueError("Meshy disconnected or timed out. It may still be processing and using credits. Resume the existing task if available; no automatic submission retry was made.") from exc
    finally:
        if owns_client: client.close()
