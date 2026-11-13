"""Download a captured CC0 full-sphere panorama, not an AI-generated ordinary-photo conversion."""
import hashlib
import io
import json
import urllib.request
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
url = "https://dl.polyhaven.org/file/ph-assets/HDRIs/extra/Tonemapped%20JPG/kiara_1_dawn.jpg"
request = urllib.request.Request(url, headers={"User-Agent": "DepthFrameAI-example/1.0"})
with urllib.request.urlopen(request, timeout=120) as response:
    data = response.read(16 * 1024 * 1024)
with Image.open(io.BytesIO(data)) as source:
    assert source.width == source.height * 2
    image = source.convert("RGB")
    image.thumbnail((4096, 2048), Image.Resampling.LANCZOS)
    target = ROOT / "examples" / "kiara-panorama.jpg"
    image.save(target, quality=92)
metadata = {"name": "Kiara 1 Dawn", "author": "Greg Zaal", "source": "https://polyhaven.com/a/kiara_1_dawn", "license": "CC0", "url": url, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "dimensions": list(image.size), "ai_generated": False}
(ROOT / "examples" / "kiara-panorama.json").write_text(json.dumps(metadata, indent=2))
print(json.dumps(metadata, indent=2))
