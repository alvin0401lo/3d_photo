"""Stage only deployable source/assets into the explicitly cloned deployment repository."""
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / '.deploy-repo'
if TARGET.resolve().parent != ROOT.resolve() or TARGET.is_symlink() or not (TARGET / '.git').is_dir():
    raise SystemExit('Expected the isolated .deploy-repo checkout inside this workspace.')
if not (ROOT / 'web_dist/index.html').is_file():
    raise SystemExit('Prepare web_dist before staging the repository.')

files = []
for name in ['streamlit_app.py', 'streamlit_ui.py', 'requirements.txt', 'models.lock.json', 'THIRD_PARTY_NOTICES.md', '.gitignore', '.env.example', 'Setup-DepthFrame.ps1', 'Start-DepthFrame.cmd', 'Start-DepthFrame.ps1', 'Stop-DepthFrame.cmd', 'Start-Streamlit.cmd', 'Test-DepthFrame.ps1']:
    files.append(Path(name))
files += [Path('.streamlit/config.toml'), Path('.streamlit/secrets.example.toml')]
for pattern in ['backend/**/*.py', 'backend/requirements*.txt', 'frontend/src/**/*', 'frontend/public/**/*', 'frontend/tests/**/*.ts', 'frontend/*.json', 'frontend/*.ts', 'frontend/*.html', 'scripts/*.py', 'scripts/*.mjs', 'examples/*', 'web_dist/**/*']:
    files.extend(path.relative_to(ROOT) for path in ROOT.glob(pattern) if path.is_file())
for name in ['Streamlit_Deployment.md', 'Object_360.md', 'Environment_360.md', 'User_Guide.md']:
    files.append(Path('docs') / name)

for relative in sorted(set(files)):
    if any(part in {'storage', 'streamlit_storage', 'artifacts', '.venv', 'node_modules', '__pycache__', '.git'} for part in relative.parts):
        raise SystemExit(f'Unexpected private/runtime path: {relative}')
    if relative.name in {'.env', 'secrets.toml'}:
        raise SystemExit('Refusing to stage a real secrets file.')
    destination = TARGET / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / relative, destination)
shutil.copyfile(ROOT / 'docs/Streamlit_README.md', TARGET / 'README.md')
print(json.dumps({'source_files_and_assets': len(set(files)) + 1, 'destination': str(TARGET), 'private_data_included': False, 'original_repository_license_preserved': (TARGET / 'LICENSE').is_file()}, indent=2))
