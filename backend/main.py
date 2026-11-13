from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import store
from .images import MAX_BYTES, decode
from .config import openai_config, meshy_config
from .objects import crop_subject


@asynccontextmanager
async def lifespan(app):
    store.init()
    store.recover_stale()
    store.cleanup_deleted()
    yield


app = FastAPI(title="DepthFrame AI", version="1.0.0", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.environ.get("DEPTHFRAME_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver").split(","))


@app.middleware("http")
async def local_boundary(request: Request, call_next):
    if request.method in {"POST", "PATCH", "DELETE", "PUT"}:
        origin = request.headers.get("origin")
        allowed = {"http://127.0.0.1:8000", "http://localhost:8000", "http://127.0.0.1:5173", "http://localhost:5173", "http://testserver"}
        same_origin = False
        if origin and os.environ.get("DEPTHFRAME_SAME_ORIGIN") == "1":
            try:
                parsed = urlsplit(origin)
                same_origin = parsed.scheme in {"http", "https"} and parsed.netloc == request.headers.get("host") and not parsed.username and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
            except ValueError:
                same_origin = False
        origin_allowed = same_origin if os.environ.get("DEPTHFRAME_HOSTED") == "1" else origin in allowed or same_origin
        if origin and not origin_allowed:
            return JSONResponse({"error": {"code": "origin_denied", "message": "This local workspace does not accept requests from other websites."}}, status_code=403)
        try:
            if int(request.headers.get("content-length", "0")) > MAX_BYTES + 1024 * 1024:
                return JSONResponse({"error": {"code": "upload_too_large", "message": "Photo exceeds the 15 MB limit."}}, status_code=413)
        except ValueError:
            return JSONResponse({"error": {"code": "invalid_length", "message": "Invalid request length."}}, status_code=400)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse({"error": {"code": f"http_{exc.status_code}", "message": str(exc.detail)}}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse({"error": {"code": "invalid_request", "message": "Some settings are invalid. Check the values and try again."}}, status_code=422)


def require_project(project_id):
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found.")
    return project


@app.get("/api/health")
def health():
    with store.connection() as db:
        row = db.execute("SELECT * FROM worker WHERE id=1").fetchone()
    worker = dict(row) if row else None
    alive = bool(worker and worker["state"] != "offline" and time.time() - worker["heartbeat"] < 45)
    lock_path = store.ROOT / "checkpoints" / "model-lock.json"
    ready = lock_path.exists() and (store.ROOT / "checkpoints" / "depth_anything_v2_vits.pth").exists()
    return {"application": "DepthFrame AI", "status": "ok", "model_ready": ready, "worker": {"alive": alive, "state": worker["state"] if alive else "offline"}, "mode": "streamlit-private-hosted" if os.environ.get("DEPTHFRAME_HOSTED") == "1" else "local-single-user"}


@app.get("/api/capabilities")
def capabilities():
    try:
        config = openai_config()
        image_api = {"configured": bool(config["api_key"]), "model": config["model"], "error": None}
    except ValueError as exc:
        image_api = {"configured": False, "model": None, "error": str(exc)}
    try:
        config = meshy_config()
        object_api = {"configured": bool(config["api_key"]), "model": config["model"], "provider": "meshy", "error": None}
    except ValueError as exc:
        object_api = {"configured": False, "model": None, "provider": "meshy", "error": str(exc)}
    return {"depth": True, "environment_360": True, "panorama_generation": image_api, "object_generation": object_api, "configuration_source": "streamlit-secrets" if os.environ.get("DEPTHFRAME_HOSTED") == "1" else "local-env", "multi_view": False, "multi_view_reason": "A panorama supports looking around a fixed viewpoint. Walkable multi-view reconstruction is not available.", "model": "Depth Anything V2 Small", "max_upload_mb": 15, "max_dimension": 4096, "max_panorama_dimension": 8192, "exports": ["original", "depth16", "preview", "raw", "bundle", "png", "glb", "browser-video", "panorama"]}


async def create_project(file: UploadFile, name=None, kind="photo"):
    data = bytearray()
    while chunk := await file.read(1024 * 1024):
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "Photo exceeds the 15 MB limit.")
    try:
        image, ext, source_hash = decode(bytes(data), panorama=kind == "panorama")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    project_id = uuid.uuid4().hex
    folder = store.project_dir(project_id)
    folder.mkdir(parents=True)
    clean_name = (name or Path((file.filename or "Untitled photo").replace("\\", "/")).stem).strip()[:100] or "Untitled photo"
    try:
        (folder / f"source.{ext}").write_bytes(data)
        image.save(folder / "image.jpg", quality=94, exif=b"")
        image.thumbnail((480, 360))
        image.save(folder / "thumbnail.webp", quality=85)
        # Re-open working dimensions: thumbnail mutates the in-memory image.
        from PIL import Image
        with Image.open(folder / "image.jpg") as working:
            width, height = working.size
        with store.connection() as db:
            db.execute("INSERT INTO projects (id,name,created,width,height,settings,source_ext,source_hash,kind) VALUES (?,?,?,?,?,?,?,?,?)", (project_id, clean_name, time.time(), width, height, json.dumps(store.DEFAULT_SETTINGS), ext, source_hash, kind))
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return store.get_project(project_id)


@app.post("/api/projects", status_code=201)
async def upload(file: UploadFile = File(...), kind: str = Query(default="photo", pattern="^(photo|panorama)$")):
    return await create_project(file, kind=kind)


@app.post("/api/examples", status_code=201)
async def example():
    from starlette.datastructures import UploadFile as StarletteUploadFile
    path = store.ROOT / "examples" / "alpine-lake.jpg"
    if not path.exists():
        raise HTTPException(503, "The example photo is missing. Run scripts/fetch_models.py to download it.")
    return await create_project(StarletteUploadFile(filename="Alpine reflections.jpg", file=io.BytesIO(path.read_bytes())), name="Alpine reflections")


@app.get("/api/example-photo")
def example_photo():
    path = store.ROOT / "examples" / "alpine-lake.jpg"
    if not path.exists():
        raise HTTPException(404, "Example photo not installed.")
    return FileResponse(path, media_type="image/jpeg")


@app.post("/api/panorama-examples", status_code=201)
async def panorama_example():
    from starlette.datastructures import UploadFile as StarletteUploadFile
    path = store.ROOT / "examples" / "kiara-panorama.jpg"
    if not path.exists():
        raise HTTPException(503, "The 360° example is not installed. Run scripts/fetch_panorama_example.py.")
    return await create_project(StarletteUploadFile(filename="Kiara dawn 360.jpg", file=io.BytesIO(path.read_bytes())), name="Kiara dawn · 360°", kind="panorama")


@app.get("/api/panorama-example-photo")
def panorama_example_photo():
    path = store.ROOT / "examples" / "kiara-panorama.jpg"
    if not path.exists():
        raise HTTPException(404, "Panorama example not installed.")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/projects")
def projects(offset: int = 0, limit: int = 50):
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422, "Invalid pagination.")
    store.recover_stale()
    store.cleanup_deleted()
    with store.connection() as db:
        ids = db.execute("SELECT id FROM projects WHERE deleting=0 ORDER BY created DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        count = db.execute("SELECT COUNT(*) FROM projects WHERE deleting=0").fetchone()[0]
    return {"items": [store.get_project(row["id"]) for row in ids], "total": count, "offset": offset}


@app.get("/api/projects/{project_id}")
def project(project_id: str):
    return require_project(project_id)


class NameChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)


@app.patch("/api/projects/{project_id}")
def rename(project_id: str, body: NameChange):
    require_project(project_id)
    if not body.name.strip():
        raise HTTPException(422, "Enter a project name.")
    with store.connection() as db:
        db.execute("UPDATE projects SET name=? WHERE id=?", (body.name.strip(), project_id))
    return require_project(project_id)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    revision: int = Field(ge=0)
    strength: float = Field(ge=0, le=1)
    motion: float = Field(ge=0, le=1)
    zoom: float = Field(ge=0.7, le=2)
    quality: str = Field(pattern="^(draft|balanced|high)$")
    autoOrbit: bool


@app.patch("/api/projects/{project_id}/settings")
def settings(project_id: str, body: Settings):
    require_project(project_id)
    values = body.model_dump(exclude={"revision"})
    with store.connection() as db:
        cursor = db.execute("UPDATE projects SET settings=?,revision=revision+1 WHERE id=? AND revision=? AND deleting=0", (json.dumps(values), project_id, body.revision))
        if cursor.rowcount != 1:
            raise HTTPException(409, "This project changed in another tab. Reopen it before saving.")
    return require_project(project_id)


@app.delete("/api/projects/{project_id}", status_code=202)
def delete(project_id: str):
    require_project(project_id)
    with store.connection() as db:
        db.execute("UPDATE projects SET deleting=1 WHERE id=?", (project_id,))
        db.execute("UPDATE jobs SET cancel=1,status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END WHERE project_id=? AND status IN ('queued','running')", (project_id,))
    store.cleanup_deleted()
    return {"status": "deleting"}


class DepthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inference_size: int = Field(default=384, ge=196, le=518)


@app.post("/api/projects/{project_id}/depth-jobs", status_code=202)
def depth(project_id: str, body: DepthRequest, request: Request):
    if require_project(project_id)["kind"] == "panorama":
        raise HTTPException(409, "This project is already a complete panorama. Open 360° view; depth inference is not required.")
    if not health()["model_ready"]:
        raise HTTPException(503, "Depth model not installed. Run the model download script, then start the worker.")
    key = request.headers.get("idempotency-key", "")[:128] or None
    try:
        return store.enqueue(project_id, key, body.inference_size)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except OverflowError as exc:
        raise HTTPException(429, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


class PanoramaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(default="", max_length=1000)
    quality: str = Field(default="medium", pattern="^(low|medium|high)$")
    allow_external_processing: bool = False


@app.post("/api/projects/{project_id}/panorama-jobs", status_code=202)
def generate_panorama(project_id: str, body: PanoramaRequest, request: Request):
    if require_project(project_id)["kind"] == "panorama":
        raise HTTPException(409, "This file is already a panorama. Open 360° view instead.")
    if not body.allow_external_processing:
        raise HTTPException(422, "Allow sending this selected photo to OpenAI before generating an environment.")
    try:
        config = openai_config()
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not config["api_key"]:
        raise HTTPException(503, "OpenAI is not configured. Add OPENAI_API_KEY to your private local .env file.")
    try:
        return store.enqueue(project_id, request.headers.get("idempotency-key", "")[:128] or None, job_type="panorama", parameters={**body.model_dump(), "deadline_seconds": config["timeout"] + 30})
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except OverflowError as exc:
        raise HTTPException(429, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


class SubjectSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)


@app.put("/api/projects/{project_id}/subject")
def select_subject(project_id: str, body: SubjectSelection):
    project = require_project(project_id)
    if project['kind'] != 'photo':
        raise HTTPException(409, "Select a subject from an ordinary photograph.")
    values = body.model_dump()
    try:
        data = crop_subject(project_id, values)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    token = hashlib.sha256(data).hexdigest()
    folder = store.project_dir(project_id) / 'subjects'
    folder.mkdir(exist_ok=True)
    (folder / (token + '.jpg')).write_bytes(data)
    selection = {**values, 'token': token, 'assets': {'preview': f'/api/projects/{project_id}/files/subject?selection={token}'}}
    with store.connection() as db:
        db.execute('UPDATE projects SET subject=? WHERE id=? AND deleting=0', (json.dumps(selection), project_id))
    return require_project(project_id)


class ObjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pose: str = Field(default="preserve", pattern="^(preserve|a-pose|t-pose)$")
    allow_external_processing: bool = False


@app.post('/api/projects/{project_id}/object-jobs', status_code=202)
def generate_object(project_id: str, body: ObjectRequest, request: Request):
    project = require_project(project_id)
    if project['kind'] != 'photo' or not project['subject']:
        raise HTTPException(422, 'Draw and confirm a selection around one person or object first.')
    if not body.allow_external_processing:
        raise HTTPException(422, 'Allow sending the selected crop to Meshy and using API credits.')
    try:
        config = meshy_config()
        if not config['api_key']:
            raise ValueError('Add MESHY_API_KEY to your private local .env file for Object 360 generation.')
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
    try:
        return store.enqueue(project_id, request.headers.get('idempotency-key', '')[:128] or None, job_type='object', parameters={**body.model_dump(), 'selection': {key: project['subject'][key] for key in ('x', 'y', 'width', 'height')}, 'model': config['model'], 'deadline_seconds': 930})
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except OverflowError as exc:
        raise HTTPException(429, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post('/api/jobs/{job_id}/resume', status_code=202)
def resume_object(job_id: str):
    current = job(job_id)
    if current['job_type'] != 'object' or not current['remote_id'] or current['status'] != 'failed':
        raise HTTPException(409, 'Only an interrupted Meshy task with a saved provider task ID can be resumed.')
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT id FROM jobs WHERE project_id=? AND status IN ('queued','running')", (current['project_id'],)).fetchone():
            raise HTTPException(409, 'Wait for this project to finish processing.')
        if db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0] >= 5:
            raise HTTPException(429, 'The queue is full.')
        db.execute("UPDATE jobs SET status='queued',stage='Resuming existing Meshy task',cancel=0,error=NULL,updated=? WHERE id=? AND status='failed'", (time.time(), job_id))
    return job(job_id)


@app.post('/api/object-examples', status_code=201)
async def object_example():
    from starlette.datastructures import UploadFile as StarletteUploadFile
    path = store.ROOT / 'examples' / 'cesium-man.jpg'
    model = store.ROOT / 'examples' / 'cesium-man.glb'
    if not path.exists() or not model.exists():
        raise HTTPException(503, 'Run scripts/fetch_object_example.py to install the credited 3D example.')
    project = await create_project(StarletteUploadFile(filename='Cesium Man 3D example.jpg', file=io.BytesIO(path.read_bytes())), name='Cesium Man · 3D example')
    queued = {'id': uuid.uuid4().hex}
    folder = store.project_dir(project['id']) / 'object' / queued['id']
    folder.mkdir(parents=True)
    shutil.copyfile(model, folder / 'model.glb')
    shutil.copyfile(path, folder / 'subject.jpg')
    result = {'job_id': queued['id'], 'provider': 'sample', 'ai_generated': False, 'model': 'Cesium Man by Cesium, CC BY 4.0', 'warning': 'Pre-existing sample model, not generated from the selected photo.', 'assets': {kind: f"/api/projects/{project['id']}/files/{kind}?job_id={queued['id']}" for kind in ('object_model', 'object_input', 'object_manifest')}}
    (folder / 'manifest.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    with store.connection() as db:
        db.execute("INSERT INTO jobs (id,project_id,status,stage,progress,created,updated,result,job_type) VALUES (?,?,'completed','Ready',100,?,?,?,'object')", (queued['id'], project['id'], time.time(), time.time(), json.dumps(result)))
    return require_project(project['id'])


@app.post("/api/projects/{project_id}/view-jobs")
def views(project_id: str):
    require_project(project_id)
    raise HTTPException(501, capabilities()["multi_view_reason"])


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    store.recover_stale()
    result = store.get_job(job_id)
    if not result:
        raise HTTPException(404, "Job not found.")
    return result


@app.post("/api/jobs/{job_id}/cancel")
def cancel(job_id: str):
    current = job(job_id)
    if current["status"] in {"queued", "running"}:
        store.update_job(job_id, cancel=1, **({"status": "cancelled", "stage": "Cancelled"} if current["status"] == "queued" else {}))
    return job(job_id)


def asset_path(project_id, kind, job_id=None, selection=None):
    project = require_project(project_id)
    folder = store.project_dir(project_id)
    simple = {"image": (folder / "image.jpg", "image/jpeg"), "original": (folder / f"source.{project['source_ext']}", f"image/{'jpeg' if project['source_ext']=='jpg' else project['source_ext']}"), "thumbnail": (folder / "thumbnail.webp", "image/webp")}
    if kind in simple:
        return simple[kind]
    if kind == 'subject':
        token = selection or (project['subject'] or {}).get('token', '')
        if len(token) != 64 or any(c not in '0123456789abcdef' for c in token):
            raise HTTPException(404, 'Select a subject first.')
        return folder / 'subjects' / (token + '.jpg'), 'image/jpeg'
    if kind in {'object_model', 'object_input', 'object_manifest'}:
        latest = project['object']
        if job_id:
            attempt = store.get_job(job_id)
            if not attempt or attempt['project_id'] != project_id or attempt['status'] != 'completed' or attempt['job_type'] != 'object':
                raise HTTPException(404, '3D object revision not found.')
            latest = attempt['result']
        if not latest:
            raise HTTPException(404, 'Generate a 3D object first.')
        filename, mime = {'object_model': ('model.glb', 'model/gltf-binary'), 'object_input': ('subject.jpg', 'image/jpeg'), 'object_manifest': ('manifest.json', 'application/json')}[kind]
        return folder / 'object' / latest['job_id'] / filename, mime
    if kind in {"panorama", "panorama_manifest"}:
        latest = project["panorama"]
        if job_id:
            attempt = store.get_job(job_id)
            if not attempt or attempt["project_id"] != project_id or attempt["status"] != "completed" or attempt["job_type"] != "panorama":
                raise HTTPException(404, "Panorama revision not found.")
            latest = attempt["result"]
        if not latest:
            raise HTTPException(404, "Generate or import a panorama first.")
        if not latest["job_id"]:
            if kind == "panorama":
                return simple["image"]
            raise HTTPException(404, "Imported panoramas have no generation manifest.")
        return folder / "panorama" / latest["job_id"] / ("panorama.png" if kind == "panorama" else "manifest.json"), "image/png" if kind == "panorama" else "application/json"
    latest = project["depth"]
    if job_id:
        attempt = store.get_job(job_id)
        if not attempt or attempt["project_id"] != project_id or attempt["status"] != "completed" or attempt["job_type"] != "depth":
            raise HTTPException(404, "Depth revision not found.")
        latest = attempt["result"]
    if not latest:
        raise HTTPException(404, "Generate depth before downloading this asset.")
    kinds = {"depth16": ("depth16.png", "image/png"), "preview": ("preview.png", "image/png"), "grid": ("grid.bin", "application/octet-stream"), "raw": ("raw_depth.npy", "application/octet-stream"), "manifest": ("manifest.json", "application/json")}
    if kind not in kinds:
        raise HTTPException(404, "Asset not found.")
    filename, mime = kinds[kind]
    return folder / "depth" / latest["job_id"] / filename, mime


@app.get("/api/projects/{project_id}/files/{kind}")
def asset(project_id: str, kind: str, download: bool = False, job_id: str | None = None, selection: str | None = None):
    path, mime = asset_path(project_id, kind, job_id, selection)
    if not path.is_file():
        raise HTTPException(404, "The asset is missing. Retry depth generation.")
    return FileResponse(path, media_type=mime, filename=path.name if download else None)


@app.get("/api/projects/{project_id}/bundle")
def bundle(project_id: str):
    project = require_project(project_id)
    if not project["depth"]:
        raise HTTPException(409, "Generate depth before exporting a project bundle.")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("settings.json", json.dumps(project["settings"], indent=2))
        archive.writestr("README.txt", "DepthFrame relative-depth photo bundle. Depth is not measured in meters. Original uploaded file and its EXIF are excluded; image.jpg is the normalized, metadata-free working photo.\n")
        for kind in ("image", "depth16", "preview", "raw", "manifest", "grid"):
            path, _ = asset_path(project_id, kind)
            if not path.is_file():
                raise HTTPException(409, "An output file is missing. Regenerate depth before exporting.")
            archive.write(path, path.name)
    return Response(buffer.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="depthframe-project.zip"'})


BUILD = store.ROOT / "frontend" / "dist"
if BUILD.is_dir():
    app.mount("/", StaticFiles(directory=BUILD, html=True), name="frontend")
