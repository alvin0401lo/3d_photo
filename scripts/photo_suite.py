"""Twelve real-photo CPU smoke cases. This checks depth outputs, not ground-truth accuracy."""
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("portrait", 415829), ("portrait", 614810),
    ("landscape", 417074), ("landscape", 1366919),
    ("street", 466685), ("street", 373912),
    ("indoor", 1571460), ("indoor", 1457842),
    ("overlapping-food", 1640777), ("overlapping-food", 1028599),
    ("low-light", 1252890), ("low-light", 3075993),
]


def main():
    folder = ROOT / "artifacts" / "photo-suite"; folder.mkdir(parents=True, exist_ok=True)
    results = []
    montage = Image.new("RGB", (1280, len(CASES) * 230), "#111111")
    draw = ImageDraw.Draw(montage)
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=60, trust_env=False) as client:
        for index, (category, photo_id) in enumerate(CASES):
            source = folder / f"{category}-{photo_id}.jpg"
            if not source.exists():
                url = f"https://images.pexels.com/photos/{photo_id}/pexels-photo-{photo_id}.jpeg?auto=compress&cs=tinysrgb&w=1024"
                request = urllib.request.Request(url, headers={"User-Agent": "DepthFrameAI-photo-tests/1.0"})
                with urllib.request.urlopen(request, timeout=60) as response:
                    source.write_bytes(response.read())
            created = client.post("/api/projects", files={"file": (source.name, source.read_bytes())}); created.raise_for_status()
            project = created.json()
            try:
                queued = client.post(f"/api/projects/{project['id']}/depth-jobs", json={"inference_size": 384}); queued.raise_for_status()
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    job = client.get(f"/api/jobs/{queued.json()['id']}").json()
                    if job["status"] in {"completed", "failed", "cancelled"}: break
                    time.sleep(.25)
                assert job["status"] == "completed", job
                result = job["result"]
                raw_response = client.get(result["assets"]["raw"]); raw_response.raise_for_status()
                raw = np.load(io.BytesIO(raw_response.content), allow_pickle=False)
                assert raw.shape == (project["height"], project["width"]) and np.isfinite(raw).all()
                assert float(np.std(raw)) > 0
                preview_response = client.get(result["assets"]["preview"]); preview_response.raise_for_status()
                preview = Image.open(io.BytesIO(preview_response.content)).convert("RGB")
                preview.save(folder / f"{category}-{photo_id}-depth.png")
                original = Image.open(source).convert("RGB")
                for x, image in ((0, original), (640, preview)):
                    fitted = ImageOps.contain(image, (620, 195))
                    montage.paste(fitted, (x + (640 - fitted.width) // 2, index * 230 + 28 + (195 - fitted.height) // 2))
                draw.text((15, index * 230 + 8), f"{category} / Pexels {photo_id} — source", fill="white")
                draw.text((655, index * 230 + 8), f"relative depth / {result['inference_seconds']:.2f} s", fill="white")
                results.append({"category": category, "pexels_photo_id": photo_id, "source_page": f"https://www.pexels.com/photo/{photo_id}/", "license": "https://www.pexels.com/license/", "dimensions": [project["width"], project["height"]], "inference_seconds": result["inference_seconds"], "tensor_dimensions": result["tensor_dimensions"], "finite_aligned_depth": True})
                print(f"PASS {category} {photo_id}: {result['inference_seconds']} s", flush=True)
            finally:
                client.delete(f"/api/projects/{project['id']}")
    montage.save(folder / "source-depth-review.jpg", quality=90)
    (folder / "report.json").write_text(json.dumps({"cases": results, "passed": len(results), "claim": "Finite source-aligned real-model depth on these inputs; not measured geometric accuracy or a multi-view consistency result."}, indent=2), encoding="utf-8")


if __name__ == "__main__": main()
