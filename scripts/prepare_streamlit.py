"""Prepare the built editor for Streamlit; never copy user data or credentials."""
from pathlib import Path
import shutil

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
print("Prepared web_dist: built application assets only; no uploaded photos or credentials.")
