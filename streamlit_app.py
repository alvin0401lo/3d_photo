"""Streamlit Community Cloud entry point, preserving the React editor and FastAPI API."""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
import subprocess
import sys

import streamlit as st
from starlette.responses import RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
# Separate the hosted workspace from the existing local app's photographs/database.
os.environ.setdefault("DEPTHFRAME_STORAGE", str(ROOT / "streamlit_storage"))
os.environ.setdefault("DEPTHFRAME_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver,*.streamlit.app")
os.environ["DEPTHFRAME_SAME_ORIGIN"] = "1"
os.environ["DEPTHFRAME_HOSTED"] = "1"

from backend import store
from backend.main import app as api

BUILD = ROOT / "web_dist"
if not (BUILD / "index.html").is_file():
    raise RuntimeError("Run npm.cmd --prefix frontend run build, then python scripts/prepare_streamlit.py before deployment.")


@asynccontextmanager
async def lifespan(app):
    # Streamlit has started its runtime before this hook. Read only provider settings.
    try:
        secrets = st.secrets.to_dict()
    except FileNotFoundError:
        secrets = {}
    for name in ("OPENAI_API_KEY", "OPENAI_IMAGE_MODEL", "OPENAI_IMAGE_TIMEOUT", "MESHY_API_KEY", "MESHY_MODEL"):
        if name in secrets:
            os.environ[name] = str(secrets[name])
    store.init()
    store.recover_stale(seconds=0)
    store.cleanup_deleted()
    logs = store.DATA / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    processes = []
    handles = []
    try:
        worker_log = (logs / "worker.log").open("a", encoding="utf-8")
        handles.append(worker_log)
        processes.append(subprocess.Popen([sys.executable, "-u", "-m", "backend.worker"], cwd=ROOT, stdout=worker_log, stderr=subprocess.STDOUT, creationflags=flags))
        model_files = [ROOT / "checkpoints/model-lock.json", ROOT / "checkpoints/depth_anything_v2_vits.pth", ROOT / ".vendor/depth-anything-v2/depth_anything_v2/dpt.py"]
        if not all(path.is_file() for path in model_files):
            setup_log = (logs / "model-setup.log").open("a", encoding="utf-8")
            handles.append(setup_log)
            processes.append(subprocess.Popen([sys.executable, "-u", "scripts/fetch_models.py"], cwd=ROOT, stdout=setup_log, stderr=subprocess.STDOUT, creationflags=flags))
        yield {"depthframe_worker_pid": processes[0].pid}
    finally:
        (store.DATA / "stop-worker").touch()
        for process in processes:
            if process.poll() is not None:
                continue
            try:
                await asyncio.to_thread(process.wait, 10)
            except subprocess.TimeoutExpired:
                process.terminate()
                await asyncio.to_thread(process.wait, 5)
        for handle in handles:
            handle.close()


async def icon(request):
    return RedirectResponse("/workspace/favicon.svg")


app = st.App(
    ROOT / "streamlit_ui.py",
    routes=[
        # Route, rather than Mount, retains the API's existing /api prefix.
        Route("/api/{path:path}", api),
        Mount("/workspace", StaticFiles(directory=BUILD, html=True)),
        Mount("/assets", StaticFiles(directory=BUILD / "assets")),
        Route("/favicon.svg", icon),
    ],
    lifespan=lifespan,
)

if __name__ == "__main__":
    app.run()
