"""Download official depth code/checkpoint and the credited example into this checkout."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "DepthFrameAI-local-setup/1.0"}), timeout=120)


def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    with request(url) as response, temp.open("wb") as output:
        while data := response.read(1024 * 1024):
            output.write(data)
    temp.replace(path)


def main():
    checkpoints = ROOT / "checkpoints"
    checkpoints.mkdir(exist_ok=True)
    lock_path = checkpoints / "model-lock.json"
    pinned = ROOT / "models.lock.json"
    previous = json.loads(pinned.read_text()) if pinned.exists() else json.loads(lock_path.read_text()) if lock_path.exists() else {}
    commit = previous.get("upstream_commit") or json.load(request("https://api.github.com/repos/DepthAnything/Depth-Anything-V2/commits/main"))["sha"]
    model_revision = previous.get("model_revision") or json.load(request("https://huggingface.co/api/models/depth-anything/Depth-Anything-V2-Small"))["sha"]
    vendor = ROOT / ".vendor" / "depth-anything-v2"
    if not (vendor / "depth_anything_v2" / "dpt.py").exists():
        print("Downloading pinned official model implementation...", flush=True)
        with request(f"https://api.github.com/repos/DepthAnything/Depth-Anything-V2/tarball/{commit}") as response:
            payload = response.read()
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for entry in archive.getmembers():
                relative = Path(*Path(entry.name).parts[1:])
                if not entry.isfile() or not relative.parts:
                    continue
                if relative.parts[0] != "depth_anything_v2" and str(relative) not in {"LICENSE", "README.md"}:
                    continue
                target = (vendor / relative).resolve()
                if not target.is_relative_to(vendor.resolve()):
                    raise ValueError("Unsafe upstream archive path")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(entry).read())
    checkpoint = checkpoints / "depth_anything_v2_vits.pth"
    if not checkpoint.exists():
        print("Downloading Depth Anything V2 Small checkpoint (~100 MB)...", flush=True)
        download(f"https://huggingface.co/depth-anything/Depth-Anything-V2-Small/resolve/{model_revision}/depth_anything_v2_vits.pth", checkpoint)
    digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    if previous.get("sha256") and digest != previous["sha256"]:
        raise ValueError("Checkpoint checksum mismatch. Remove the damaged checkpoint and run setup again.")
    lock = {"model": "Depth Anything V2 Small", "license": "Apache-2.0", "upstream_commit": commit, "model_revision": model_revision, "sha256": digest}
    lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    sample = ROOT / "examples" / "alpine-lake.jpg"
    if not sample.exists():
        print("Downloading the example photo...", flush=True)
        download("https://images.pexels.com/photos/417074/pexels-photo-417074.jpeg?auto=compress&cs=tinysrgb&w=1600", sample)
    print(json.dumps(lock, indent=2), flush=True)
    print("Model and example photo are ready. No further network access is required for local inference.")


if __name__ == "__main__":
    main()
