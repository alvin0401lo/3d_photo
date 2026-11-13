"""Prepare the built editor for Streamlit; never copy user data or credentials."""
from pathlib import Path
import shutil
import json

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "frontend" / "dist"
target = ROOT / "web_dist"
if not (source / "index.html").is_file():
    raise SystemExit("Build the frontend first: npm.cmd --prefix frontend run build")
if target.resolve().parent != ROOT.resolve() or target.is_symlink():
    raise SystemExit("Unsafe output directory")
if target.exists():
    shutil.rmtree(target)
shutil.copytree(source, target)
modules = ROOT / 'frontend' / 'node_modules'
pending = list(json.loads((ROOT / 'frontend/package.json').read_text())['dependencies'])
seen = set()
notices = []
while pending:
    name = pending.pop()
    if name in seen:
        continue
    seen.add(name)
    package = modules / name
    metadata = package / 'package.json'
    if not metadata.is_file():
        continue
    info = json.loads(metadata.read_text(encoding='utf-8'))
    pending.extend(info.get('dependencies', {}))
    for path in package.iterdir():
        if path.is_file() and path.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'OFL')):
            notices.append(f"{name} {info['version']} — {path.name}\n{path.read_text(encoding='utf-8')}\n")
(target / 'THIRD_PARTY_LICENSES.txt').write_text('\n'.join(notices), encoding='utf-8')
print("Prepared web_dist: built application assets only; no uploaded photos or credentials.")
