"""One local launcher; Ctrl+C shuts down only the processes it started."""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        raise SystemExit("The frontend is not built. Run Setup-DepthFrame.ps1 first.")
    if not (ROOT / "checkpoints" / "model-lock.json").exists():
        raise SystemExit("The model is missing. Run Setup-DepthFrame.ps1 first.")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=2) as response:
            if response.status == 200 and json.load(response).get("application") == "DepthFrame AI":
                print("DepthFrame is already running: http://127.0.0.1:8000")
                if not args.no_browser: webbrowser.open("http://127.0.0.1:8000")
                return
    except OSError:
        pass
    logs = ROOT / "storage" / "logs"; logs.mkdir(parents=True, exist_ok=True)
    stop_file = ROOT / "storage" / "stop-application"
    stop_file.unlink(missing_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with (logs / "worker.log").open("a", encoding="utf-8") as worker_log, (logs / "api.log").open("a", encoding="utf-8") as api_log:
        worker = subprocess.Popen([sys.executable, "-u", "-m", "backend.worker"], cwd=ROOT, stdout=worker_log, stderr=subprocess.STDOUT, creationflags=flags)
        server = subprocess.Popen([sys.executable, "-u", "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT, stdout=api_log, stderr=subprocess.STDOUT, creationflags=flags)
        try:
            for _ in range(40):
                if worker.poll() is not None or server.poll() is not None:
                    raise RuntimeError("A service stopped. Check storage/logs for details.")
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=1) as response:
                        if response.status == 200: break
                except OSError:
                    time.sleep(0.5)
            else:
                raise RuntimeError("DepthFrame did not start within 20 seconds. Check storage/logs.")
            print("\nDepthFrame AI is ready: http://127.0.0.1:8000\nCPU depth stays local. Optional OpenAI / Meshy generation sends selected input only when requested with consent.\nPress Ctrl+C to stop both services.\n", flush=True)
            if not args.no_browser: webbrowser.open("http://127.0.0.1:8000")
            while worker.poll() is None and server.poll() is None and not stop_file.exists():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping DepthFrame...", flush=True)
        finally:
            (ROOT / "storage" / "stop-worker").touch()
            try: worker.wait(timeout=10)
            except subprocess.TimeoutExpired: worker.terminate(); worker.wait(timeout=5)
            if server.poll() is None:
                server.terminate(); server.wait(timeout=5)
            stop_file.unlink(missing_ok=True)


if __name__ == "__main__": main()
