"""Live real-model smoke test against a running local API + worker."""
import io
import json
import time
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30, trust_env=False) as client:
        health = client.get("/api/health").json()
        assert health["model_ready"] and health["worker"]["alive"], health
        created = client.post("/api/examples")
        created.raise_for_status()
        project = created.json()
        queued = client.post(f"/api/projects/{project['id']}/depth-jobs", json={"inference_size": 384}, headers={"Idempotency-Key": "real-smoke-test"})
        queued.raise_for_status()
        job_id = queued.json()["id"]
        started = time.monotonic()
        stage = None
        while time.monotonic() - started < 330:
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["stage"] != stage:
                stage = job["stage"]; print(stage, flush=True)
            if job["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(1)
        assert job["status"] == "completed", job
        result = job["result"]
        raw_response = client.get(result["assets"]["raw"]); raw_response.raise_for_status()
        raw = np.load(io.BytesIO(raw_response.content), allow_pickle=False)
        assert raw.shape == (project["height"], project["width"])
        assert np.isfinite(raw).all() and float(np.std(raw)) > 0
        depth_response = client.get(result["assets"]["depth16"]); depth_response.raise_for_status()
        depth = np.asarray(Image.open(io.BytesIO(depth_response.content)))
        assert depth.max() > 255 and depth.shape == raw.shape
        grid = client.get(result["assets"]["grid"]); grid.raise_for_status()
        assert len(grid.content) == result["grid_width"] * result["grid_height"] * 4
        assert np.isfinite(np.frombuffer(grid.content, dtype="<f4")).all()
        assert result["model"]["sha256"] == json.loads((ROOT / "checkpoints" / "model-lock.json").read_text())["sha256"]
        # This landscape has sky at top and the nearby lake at bottom.
        foreground = float(np.median(depth[-depth.shape[0] // 5:]))
        background = float(np.median(depth[:depth.shape[0] // 8]))
        assert foreground > background, {"foreground": foreground, "background": background}
        bundle = client.get(f"/api/projects/{project['id']}/bundle"); bundle.raise_for_status()
        evidence = ROOT / "artifacts"; evidence.mkdir(exist_ok=True)
        (evidence / "real-model-smoke.json").write_text(json.dumps({"project_id": project["id"], "job_id": job_id, "elapsed_seconds": round(time.monotonic() - started, 3), "foreground_depth16_median": foreground, "sky_depth16_median": background, "result": result, "checks": "real CPU model, finite raw array, source-sized PNG16, grid byte count, checkpoint hash, near/far ordering, ZIP download"}, indent=2), encoding="utf-8")
        (ROOT / "examples" / "alpine-depth.png").write_bytes(client.get(result["assets"]["preview"]).content)
        print(f"PASS: real CPU model, project {project['id']}, inference {result['inference_seconds']} s", flush=True)


if __name__ == "__main__": main()
