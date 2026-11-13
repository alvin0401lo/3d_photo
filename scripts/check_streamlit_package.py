"""Cold-start the staged deployment in isolated storage, then run real CPU depth."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT / '.deploy-repo'
BASE = 'http://127.0.0.1:8502'


def request(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    call = urllib.request.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(call, timeout=5) as response:
        return json.load(response)


def main():
    if not (CHECKOUT / 'streamlit_app.py').is_file():
        raise SystemExit('Stage the deployment repository first.')
    try:
        request('/api/health')
    except (OSError, ValueError):
        pass
    else:
        raise SystemExit('Test port 8502 is already in use; leave the existing service untouched.')
    with tempfile.TemporaryDirectory(prefix='streamlit-package-', dir=ROOT / 'artifacts') as temporary:
        storage = Path(temporary)
        env = {**os.environ, 'DEPTHFRAME_STORAGE': str(storage)}
        log_path = ROOT / 'artifacts/streamlit-package-server.log'
        with log_path.open('w', encoding='utf-8') as output:
            process = subprocess.Popen([sys.executable, '-m', 'streamlit', 'run', 'streamlit_app.py', '--server.headless=true', '--server.address=127.0.0.1', '--server.port=8502'], cwd=CHECKOUT, env=env, stdout=output, stderr=subprocess.STDOUT)
            started = time.monotonic()
            try:
                while time.monotonic() - started < 180:
                    if process.poll() is not None: raise AssertionError('Staged app stopped. Inspect its server log.')
                    try:
                        health = request('/api/health')
                        if health['worker']['alive'] and health['model_ready']: break
                    except OSError:
                        pass
                    time.sleep(1)
                else: raise AssertionError('The first-start model setup did not become ready within 180 seconds.')
                print('Staged app and model ready; running real CPU depth.', flush=True)
                project = request('/api/examples', {})
                job = request(f"/api/projects/{project['id']}/depth-jobs", {'inference_size': 384})
                until = time.monotonic() + 90
                while time.monotonic() < until:
                    state = request('/api/jobs/' + job['id'])
                    if state['status'] in ('completed', 'failed', 'cancelled'): break
                    time.sleep(.5)
                assert state['status'] == 'completed', state.get('error')
                result = state['result']
                with urllib.request.urlopen(BASE + result['assets']['grid'], timeout=5) as response:
                    grid = np.frombuffer(response.read(), dtype='<f4')
                assert grid.size == result['grid_width'] * result['grid_height'] and np.isfinite(grid).all()
                report = {'staged_source_starts': True, 'isolated_storage': True, 'cpu_model_ready': True, 'real_depth_completed': True, 'finite_depth_grid': True, 'model_sha256': result['model']['sha256'], 'elapsed_seconds': round(time.monotonic() - started, 2)}
                (ROOT / 'artifacts/streamlit-package-check.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                print(json.dumps(report, indent=2))
            finally:
                (storage / 'stop-worker').touch()
                time.sleep(2)
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                else:
                    process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)


if __name__ == '__main__': main()
