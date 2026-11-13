"""Credited pre-existing character model for orbit controls, not an AI photo reconstruction."""
import hashlib
import io
import json
import urllib.request
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/CesiumMan/'
for remote, name in [('glTF-Binary/CesiumMan.glb', 'cesium-man.glb'), ('screenshot/screenshot.gif', 'cesium-man.jpg')]:
    request = urllib.request.Request(BASE + remote, headers={'User-Agent': 'DepthFrameAI-example/1.0'})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(16 * 1024 * 1024)
    target = ROOT / 'examples' / name
    if name.endswith('.jpg'):
        with Image.open(io.BytesIO(data)) as source:
            source.seek(0)
            source.convert('RGB').save(target, quality=94)
    else:
        assert data[:4] == b'glTF'
        target.write_bytes(data)
metadata = {'title': 'Cesium Man', 'author': 'Cesium', 'source': 'https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CesiumMan', 'license': 'CC BY 4.0; Cesium logo retains its separate trademark notice', 'ai_generated': False, 'note': 'Pre-existing sample character; not reconstructed from a selected photo.', 'sha256': hashlib.sha256((ROOT / 'examples' / 'cesium-man.glb').read_bytes()).hexdigest()}
(ROOT / 'examples' / 'cesium-man.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
print('Installed credited Cesium Man GLB and reference screenshot.')
