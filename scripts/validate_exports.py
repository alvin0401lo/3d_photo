"""Independently reopen the artifacts downloaded by the browser tests."""
import io
import json
import struct
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ARTIFACTS = ROOT / "artifacts"


def main():
    still = Image.open(ARTIFACTS / "example-3d.png")
    still.load()
    assert still.width > 100 and still.height > 100
    depth = np.asarray(Image.open(ARTIFACTS / "example-depth16.png"))
    assert depth.max() > 255 and depth.ndim == 2
    assert (ARTIFACTS / "example-original.jpg").read_bytes() == (ROOT / "examples" / "alpine-lake.jpg").read_bytes()
    with zipfile.ZipFile(ARTIFACTS / "example-project.zip") as bundle:
        raw = np.load(io.BytesIO(bundle.read("raw_depth.npy")), allow_pickle=False)
        assert raw.shape == depth.shape and np.isfinite(raw).all()
        assert json.loads(bundle.read("settings.json"))["strength"] == 0.62
        assert not any(name.startswith("source.") for name in bundle.namelist())
    glb = (ARTIFACTS / "example-scene.glb").read_bytes()
    magic, version, length = struct.unpack_from("<4sII", glb)
    assert magic == b"glTF" and version == 2 and length == len(glb)
    json_length = struct.unpack_from("<I", glb, 12)[0]
    document = json.loads(glb[20:20 + json_length])
    assert document["images"][0]["bufferView"] >= 0 and document["meshes"]
    assert all(view.get("byteOffset", 0) + view["byteLength"] <= document["buffers"][view["buffer"]]["byteLength"] for view in document["bufferViews"])
    capture = cv2.VideoCapture(str(ARTIFACTS / "example-orbit.webm"))
    frames = 0; timestamps = []; first = None; last = None
    while True:
        ok, frame = capture.read()
        if not ok: break
        assert frame.shape[:2] == (720, 1280)
        frames += 1; timestamps.append(capture.get(cv2.CAP_PROP_POS_MSEC))
        if first is None: first = frame
        last = frame
    capture.release()
    assert frames >= 10, f"Only {frames} frames could be decoded."
    duration = (max(timestamps) - min(timestamps)) / 1000
    assert 4 <= duration <= 7, f"Unexpected video duration: {duration} s"
    assert float(np.std(first)) > 5 and float(np.std(last)) > 5, "Video contains empty frames."
    panorama = Image.open(ARTIFACTS / "360-export.jpg")
    panorama.load()
    panorama_still = Image.open(ARTIFACTS / "360-still.png")
    panorama_still.load()
    assert panorama.width == 2 * panorama.height and panorama.size == (4096, 2048)
    assert float(np.std(np.asarray(panorama_still))) > 10, "360 still is blank."
    report = {"png": {"dimensions": still.size, "opens": True}, "depth16": {"dimensions": list(reversed(depth.shape)), "max": int(depth.max()), "opens": True}, "original_bytes_match": True, "bundle_raw_depth_and_settings": True, "glb_embedded_texture_and_buffer_bounds": True, "video": {"frames": frames, "duration_seconds": round(duration, 3), "dimensions": [1280, 720], "decodes": True}}
    report["panorama"] = {"dimensions": panorama.size, "opens": True, "still_dimensions": panorama_still.size, "nonempty_still": True}
    from backend.objects import validate_glb
    object_model = (ARTIFACTS / "object-model.glb").read_bytes()
    object_document = validate_glb(object_model)
    object_still = Image.open(ARTIFACTS / "object-still.png")
    object_still.load()
    assert object_model == (ROOT / "examples" / "cesium-man.glb").read_bytes()
    assert float(np.std(np.asarray(object_still))) > 10, "Object still is blank."
    report["object"] = {"sample_model_bytes_preserved": True, "mesh_count": len(object_document['meshes']), "still_dimensions": object_still.size, "nonempty_still": True}
    (ARTIFACTS / "export-validation.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__": main()
