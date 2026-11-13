"""Exercise a real worker in disposable, isolated storage: cancel, crash recovery, timeout."""
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["DEPTHFRAME_STORAGE"] = str(ROOT / "artifacts" / "worker-check-storage")
sys.path.insert(0, str(ROOT))
from backend import store
from backend.main import app
from fastapi.testclient import TestClient


def wait_for(predicate, seconds=45):
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        result = predicate()
        if result: return result
        time.sleep(.1)
    raise AssertionError("Timed out waiting for worker state")


def start_worker(timeout=300):
    env = {**os.environ, "DEPTHFRAME_JOB_TIMEOUT": str(timeout)}
    return subprocess.Popen([sys.executable, "-m", "backend.worker"], cwd=ROOT, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def stop_worker(worker):
    (store.DATA / "stop-worker").touch()
    worker.wait(timeout=12)


def main():
    report = {}
    with TestClient(app) as client:
        source = (ROOT / "examples" / "alpine-lake.jpg").read_bytes()
        project = client.post("/api/projects", files={"file": ("worker-check.jpg", source)}).json()
        # Cancellation while queued publishes no assets.
        queued = store.enqueue(project["id"])
        client.post(f"/api/jobs/{queued['id']}/cancel")
        assert store.get_job(queued["id"])["status"] == "cancelled"
        assert not (store.project_dir(project["id"]) / "depth").exists()
        report["queued_cancellation"] = True
        # Simulate an interrupted, claimed job with no owning worker. A new singleton recovers it.
        interrupted = store.enqueue(project["id"])
        store.claim()
        worker = start_worker()
        try:
            wait_for(lambda: store.get_job(interrupted["id"])["status"] == "failed")
            report["restart_recovers_interrupted_attempt"] = True
            retry = store.enqueue(project["id"])
            wait_for(lambda: store.get_job(retry["id"])["status"] in {"completed", "failed"}, 90)
            assert store.get_job(retry["id"])["status"] == "completed", store.get_job(retry["id"])
            report["real_model_retry_after_restart"] = True
            # A deletion while running must hide the project and prevent output publication.
            deleting = store.enqueue(project["id"])
            wait_for(lambda: store.get_job(deleting["id"])["status"] == "running")
            assert client.delete(f"/api/projects/{project['id']}").status_code == 202
            wait_for(lambda: not store.project_dir(project["id"]).exists(), 45)
            assert store.get_project(project["id"]) is None
            report["delete_during_real_inference"] = True
        finally:
            stop_worker(worker)
        # A deliberately zero-second deadline tests actual child termination and durable failure.
        deadline_project = client.post("/api/projects", files={"file": ("deadline.jpg", source)}).json()
        deadline_job = store.enqueue(deadline_project["id"])
        worker = start_worker(timeout=0)
        try:
            wait_for(lambda: store.get_job(deadline_job["id"])["status"] == "failed")
            assert "deadline" in store.get_job(deadline_job["id"])["error"]
            report["hard_deadline_terminates_child"] = True
        finally:
            stop_worker(worker)
        client.delete(f"/api/projects/{deadline_project['id']}")
    (ROOT / "artifacts" / "worker-checks.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__": main()
