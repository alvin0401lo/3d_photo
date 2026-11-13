"""Actual Depth Anything V2 Small CPU inference; no fallback or simulated depth."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from . import store


def normalize_depth(raw):
    raw = np.asarray(raw, dtype=np.float32)
    if raw.ndim != 2 or not np.isfinite(raw).all():
        raise ValueError("Model returned an invalid depth field.")
    low, high = np.percentile(raw, (2, 98)).astype(float)
    if high - low < 1e-7:
        normalized = np.zeros_like(raw)
    else:
        normalized = np.clip((raw - low) / (high - low), 0, 1)
    return normalized.astype(np.float32), {"percentile_low": 2, "percentile_high": 98, "low": low, "high": high, "near": 1, "far": 0, "units": "relative, not meters"}


class DepthModel:
    def __init__(self):
        import torch
        sys.path.insert(0, str(store.ROOT / ".vendor" / "depth-anything-v2"))
        from depth_anything_v2.dpt import DepthAnythingV2

        checkpoint = store.ROOT / "checkpoints" / "depth_anything_v2_vits.pth"
        self.lock = json.loads((checkpoint.parent / "model-lock.json").read_text())
        digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        if digest != self.lock["sha256"]:
            raise ValueError("Model checksum mismatch. Run setup again.")
        torch.set_num_threads(max(1, min(8, int(os.environ.get("DEPTHFRAME_CPU_THREADS", "4")))))
        self.model = DepthAnythingV2(encoder="vits", features=64, out_channels=[48, 96, 192, 384])
        self.model.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=True))
        self.model.to("cpu").eval()

    def run(self, job, send):
        import cv2
        import torch
        import torch.nn.functional as F

        started = time.monotonic()
        folder = store.project_dir(job["project_id"])
        with Image.open(folder / "image.jpg") as image:
            rgb = np.asarray(image.convert("RGB"))
        height, width = rgb.shape[:2]
        # Fit the tensor within both a short-side target and a 768px long-side cap.
        scale = min(job["inference_size"] / min(width, height), 768 / max(width, height))
        tensor_width = max(14, round(width * scale / 14) * 14)
        tensor_height = max(14, round(height * scale / 14) * 14)
        resized = cv2.resize(rgb, (tensor_width, tensor_height), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
        normalized_rgb = (resized - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
        tensor = torch.from_numpy(np.ascontiguousarray(normalized_rgb.transpose(2, 0, 1))).unsqueeze(0)
        send({"stage": "Estimating depth on CPU", "progress": 20})
        inference_started = time.monotonic()
        with torch.inference_mode():
            prediction = self.model(tensor)
            raw = F.interpolate(prediction[:, None], (height, width), mode="bilinear", align_corners=True)[0, 0].cpu().numpy().astype(np.float32)
        inference_seconds = time.monotonic() - inference_started
        send({"stage": "Preparing depth assets", "progress": 80})
        depth, normalization = normalize_depth(raw)
        revision = folder / "depth" / job["id"]
        temp = folder / "depth" / (job["id"] + ".tmp")
        temp.mkdir(parents=True, exist_ok=True)
        np.save(temp / "raw_depth.npy", raw, allow_pickle=False)
        Image.fromarray(np.round(depth * 65535).astype(np.uint16)).save(temp / "depth16.png")
        Image.fromarray(np.round(depth * 255).astype(np.uint8)).save(temp / "preview.png")
        grid_width = max(2, min(512, width))
        grid_height = max(2, min(512, height))
        grid = cv2.resize(depth, (grid_width, grid_height), interpolation=cv2.INTER_AREA).astype("<f4")
        grid.tofile(temp / "grid.bin")
        result = {
            "project_id": job["project_id"], "job_id": job["id"], "created_at": time.time(), "width": width, "height": height,
            "grid_width": grid_width, "grid_height": grid_height,
            "grid_dtype": "float32-le", "origin": "top-left", "normalization": normalization,
            "model": self.lock, "input_sha256": hashlib.sha256((folder / "image.jpg").read_bytes()).hexdigest(),
            "inference_size": job["inference_size"], "tensor_dimensions": [tensor_height, tensor_width],
            "inference_seconds": round(inference_seconds, 3), "processing_seconds": round(time.monotonic() - started, 3),
            "pipeline_version": "1.0.0", "representation": "relative-depth-photo-mesh",
            "runtime": {"torch": torch.__version__, "opencv": cv2.__version__, "numpy": np.__version__, "cpu_threads": torch.get_num_threads()},
            "camera": {"fov_degrees": 40, "position": [0, 0, 3], "world_up": "+y", "camera_forward": "-z", "units": "arbitrary"},
        }
        result["assets"] = {kind: f"/api/projects/{job['project_id']}/files/{kind}?job_id={job['id']}" for kind in ("depth16", "preview", "raw", "grid", "manifest")}
        (temp / "manifest.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        send({"stage": "Saving result", "progress": 95})
        temp.rename(revision)
        return result
