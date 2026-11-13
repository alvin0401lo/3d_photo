"""Local API/queue regression tests. Synthetic depth fixtures are explicitly not AI validation."""
import io
import json
import time
import uuid
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend import main, store
from backend.depth import normalize_depth


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path / "test-storage")
    with TestClient(main.app) as api:
        yield api


def photo(format="PNG", size=(80, 60)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (100, 150, 200)).save(buffer, format=format)
    return buffer.getvalue()


def create(client, data=None, filename="photo.png"):
    response = client.post("/api/projects", files={"file": (filename, data if data is not None else photo())})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("format,extension", [("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")])
def test_upload_and_durable_gallery(client, format, extension):
    data = photo(format)
    project = create(client, data, "untrusted-name.exe")
    assert project["source_ext"] == extension
    assert project["width"] == 80 and project["height"] == 60
    assert client.get(project["assets"]["original"]).content == data
    assert client.get("/api/projects").json()["total"] == 1
    store.init()
    assert client.get(f"/api/projects/{project['id']}").json()["name"] == "untrusted-name"
    assert client.get(project["assets"]["thumbnail"]).headers["content-type"] == "image/webp"


@pytest.mark.parametrize("data", [b"not a photo", b"", photo("GIF"), photo(size=(4097, 32)), photo(size=(31, 50))])
def test_bad_uploads_leave_no_project(client, data):
    assert client.post("/api/projects", files={"file": ("bad.jpg", data)}).status_code == 422
    assert client.get("/api/projects").json()["total"] == 0


def test_exif_orientation_alpha_and_animation(client):
    image = Image.new("RGB", (90, 60), "red")
    exif = Image.Exif(); exif[274] = 6
    data = io.BytesIO(); image.save(data, format="JPEG", exif=exif)
    project = create(client, data.getvalue())
    assert (project["width"], project["height"]) == (60, 90)
    working = Image.open(io.BytesIO(client.get(project["assets"]["image"]).content))
    assert not working.getexif()
    alpha = io.BytesIO(); Image.new("RGBA", (40, 40), (0, 0, 0, 0)).save(alpha, "PNG")
    transparent = create(client, alpha.getvalue())
    working = Image.open(io.BytesIO(client.get(transparent["assets"]["image"]).content))
    assert min(working.getpixel((0, 0))) >= 250
    animated = io.BytesIO(); Image.new("RGB", (40, 40), "red").save(animated, "PNG", save_all=True, append_images=[Image.new("RGB", (40, 40), "blue")], duration=100)
    assert client.post("/api/projects", files={"file": ("animated.png", animated.getvalue())}).status_code == 422


def test_upload_limits_and_local_security(client):
    assert client.post("/api/projects", content=b"x", headers={"content-length": str(17 * 1024 * 1024), "content-type": "application/octet-stream"}).status_code == 413
    assert client.post("/api/projects", files={"file": ("photo.png", photo())}, headers={"Origin": "https://malicious.example"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    project = create(client)
    assert client.get(f"/api/projects/{project['id']}/files/..%2F..%2FREADME.md").status_code == 404
    assert client.get(f"/api/projects/{project['id']}/files/unknown").status_code == 404


def test_settings_revision_and_rename(client):
    project = create(client)
    path = f"/api/projects/{project['id']}"
    settings = {**project["settings"], "revision": 0, "strength": 0.72}
    saved = client.patch(path + "/settings", json=settings)
    assert saved.status_code == 200 and saved.json()["revision"] == 1
    assert saved.json()["settings"]["strength"] == 0.72
    assert client.patch(path + "/settings", json=settings).status_code == 409
    assert client.patch(path + "/settings", json={**settings, "strength": 2}).status_code == 422
    assert client.patch(path + "/settings", json={**settings, "quality": "invalid"}).status_code == 422
    assert client.patch(path, json={"name": "New photo"}).json()["name"] == "New photo"
    assert client.patch(path, json={"name": "   "}).status_code == 422


def test_queue_idempotency_claim_cancel_and_retry(client):
    project = create(client)
    first = store.enqueue(project["id"], "same-key")
    assert store.enqueue(project["id"], "same-key")["id"] == first["id"]
    assert store.enqueue(project["id"], "another-key")["id"] == first["id"]
    claimed = store.claim()
    assert claimed["id"] == first["id"] and store.claim() is None
    assert client.post(f"/api/jobs/{first['id']}/cancel").status_code == 200
    assert store.cancel_requested(first["id"])
    store.update_job(first["id"], status="cancelled", stage="Cancelled")
    second = store.enqueue(project["id"], "retry-key")
    assert second["id"] != first["id"]
    client.post(f"/api/jobs/{second['id']}/cancel")
    assert store.get_job(second["id"])["status"] == "cancelled"


def test_queue_limit_and_stale_recovery(client):
    for i in range(5):
        store.enqueue(create(client)["id"])
    with pytest.raises(OverflowError):
        store.enqueue(create(client)["id"])
    running = store.claim()
    with store.connection() as db:
        db.execute("UPDATE jobs SET updated=? WHERE id=?", (time.time() - 100, running["id"]))
    store.recover_stale()
    assert store.get_job(running["id"])["status"] == "failed"
    assert store.get_job(running["id"])["error"]


def test_delete_waits_for_active_writer(client):
    project = create(client)
    job = store.enqueue(project["id"])
    store.claim()
    folder = store.project_dir(project["id"])
    assert client.delete(f"/api/projects/{project['id']}").status_code == 202
    assert folder.exists()
    assert store.cancel_requested(job["id"])
    assert client.get(f"/api/projects/{project['id']}").status_code == 404
    assert client.get(project["assets"]["image"]).status_code == 404
    store.update_job(job["id"], status="cancelled")
    store.cleanup_deleted()
    assert not folder.exists()
    with pytest.raises(LookupError):
        store.enqueue(project["id"])


def test_depth_normalization_and_invalid_fields():
    raw = np.array([[0, 1], [2, 3]], dtype=np.float32)
    normalized, metadata = normalize_depth(raw)
    assert normalized[0, 0] == 0 and normalized[1, 1] == 1
    assert metadata["near"] == 1 and np.isfinite(normalized).all()
    assert np.array_equal(normalize_depth(np.ones((3, 4)))[0], np.zeros((3, 4)))
    with pytest.raises(ValueError): normalize_depth(np.array([[np.nan]]))
    with pytest.raises(ValueError): normalize_depth(np.ones(4))


def test_depth_revision_and_bundle_fixture(client):
    project = create(client)
    job = store.enqueue(project["id"])
    folder = store.project_dir(project["id"]) / "depth" / job["id"]
    folder.mkdir(parents=True)
    for name in ("depth16.png", "preview.png", "raw_depth.npy", "manifest.json", "grid.bin"):
        (folder / name).write_bytes(b"explicit synthetic asset fixture")
    result = {"job_id": job["id"], "fixture": True}
    store.update_job(job["id"], status="completed", result=json.dumps(result))
    response = client.get(f"/api/projects/{project['id']}/bundle")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
        assert {"settings.json", "image.jpg", "raw_depth.npy", "depth16.png", "manifest.json"} <= set(bundle.namelist())
        assert not any(name.startswith("source.") for name in bundle.namelist())
    assert client.get(f"/api/projects/{project['id']}/files/raw?job_id={uuid.uuid4().hex}").status_code == 404


def test_capabilities_missing_project_and_no_fake_multiview(client):
    assert client.get("/api/capabilities").json()["multi_view"] is False
    assert client.get("/api/projects/nonexistent").status_code == 404
    assert client.get("/api/jobs/nonexistent").status_code == 404
    assert client.get("/api/projects?limit=101").status_code == 422
    project = create(client)
    assert client.post(f"/api/projects/{project['id']}/view-jobs").status_code == 501
    assert client.get(f"/api/projects/{project['id']}/bundle").status_code == 409


def test_health_marks_offline_and_stale_workers_unavailable(client):
    store.heartbeat("offline")
    assert not client.get("/api/health").json()["worker"]["alive"]
    store.heartbeat("ready")
    state = client.get("/api/health").json()
    assert state["application"] == "DepthFrame AI" and state["worker"]["alive"]
    with store.connection() as db:
        db.execute("UPDATE worker SET heartbeat=?", (time.time() - 100,))
    assert not client.get("/api/health").json()["worker"]["alive"]


def test_locked_file_deletion_retains_tombstone_then_retries(client, monkeypatch):
    project = create(client)
    original = store.shutil.rmtree
    def file_locked(*args, **kwargs):
        raise PermissionError("Simulated Windows sharing violation")
    monkeypatch.setattr(store.shutil, "rmtree", file_locked)
    assert client.delete(f"/api/projects/{project['id']}").status_code == 202
    assert store.project_dir(project["id"]).exists()
    assert store.get_project(project["id"]) is None
    monkeypatch.setattr(store.shutil, "rmtree", original)
    store.cleanup_deleted()
    assert not store.project_dir(project["id"]).exists()
