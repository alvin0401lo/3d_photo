# Streamlit deployment

Repository: **https://github.com/alvin0401lo/3d_photo**

The deployment uses Streamlit 1.67's supported `st.App` ASGI integration. `streamlit_app.py` mounts the existing FastAPI endpoints and compiled React/Three.js editor on the same port. `streamlit_ui.py` provides the Streamlit page; `/workspace/` opens the full editor. Node is needed to rebuild the editor locally, but not at cloud startup because `web_dist/` contains the compiled assets.

## Community Cloud settings

1. Sign in at **https://share.streamlit.io/** with the GitHub account that administers the repository.
2. Choose **Create app → Yup, I have an app**.
3. Set repository **alvin0401lo/3d_photo**, branch **main**, and entrypoint **streamlit_app.py**.
4. In Advanced settings, select **Python 3.12**. If you want live AI generation, add the desired keys privately using the format in `.streamlit/secrets.example.toml`. Do not upload `.env` or actual `secrets.toml` to GitHub.
5. Deploy, then set **private app access** in Community Cloud before using personal photos or configured paid API keys. This application is still a single-user workspace, not a public multi-tenant service. A public source repository does not mean the running app should be public.
6. Open the assigned `*.streamlit.app` URL and check the editor, Object 360 sample, Environment 360 sample, and CPU example. The CPU model downloads on first startup; inspect app logs if it is not ready.

Minimal optional secrets:

```toml
MESHY_API_KEY = "your-private-meshy-key"
MESHY_MODEL = "meshy-7.1"
OPENAI_API_KEY = "your-private-openai-key"
OPENAI_IMAGE_MODEL = "gpt-image-2.5-sunburst"
OPENAI_IMAGE_TIMEOUT = 300
```

Either provider can be omitted. Examples and panorama import do not require a key. Generation requires the existing consent checkbox and uses the configured provider account's credits. Keys are read on the server and are never included in the frontend bundle. Live provider generation is not established by contract mocks or captured/sample assets.

## Run locally through Streamlit

```powershell
cd C:\AAI\Project4Fun\3d_photo
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe scripts/prepare_streamlit.py
.\Start-Streamlit.cmd
```

Open **http://127.0.0.1:8501**. The existing FastAPI launcher remains available on port 8000. Streamlit uses a separate `streamlit_storage/` directory, preserving the existing local application's `storage/` projects.

## Data and limits

- Community Cloud disk is temporary. Download originals, results, and manifests before restarting/redeploying; this is not durable cloud backup.
- The built-in private-workspace assumption must be enforced with Community Cloud's app access controls. The app does not implement user accounts or per-user project isolation.
- CPU inference runs in one background worker. The Small checkpoint and pinned source download once when absent. Actual startup/memory behavior on the selected cloud machine must be checked after deployment.
- `websockets==16.1.1` is pinned for compatibility with the existing Uvicorn version behind reverse proxies. Do not remove this pin without checking Streamlit's runtime warnings.
- The development agent API is enabled only by an explicit local test flag; it is not enabled in the committed deployment configuration.

## Verification

The local Streamlit launch is checked through its agent API and through browser tests against the same mounted editor. The browser suite includes the Streamlit iframe, real object orbiting and downloads, all existing photo/panorama workflows, and real CPU depth. Linux/Python 3.12 dependency resolution is checked separately; it is not a substitute for observing a live Community Cloud deployment.

Executed release checks: **62 automated cases** (47 backend/Streamlit shell, 5 geometry, 10 browser scenarios), real worker recovery/deletion/deadline checks, independently reopened downloads, production build, Python compilation, dependency consistency, and deployment-file type checks. The local agent API returned `ready`; the normal preview has that development API disabled. Existing local project IDs remained available. Evidence is retained locally in `artifacts/streamlit-release-checks.log`, `streamlit-agent-check.json`, and `streamlit-linux-dependencies.log`; runtime artifacts are not published in the repository.

The staged repository was also started without a pre-existing model/source cache, using isolated test storage. Its first-start download completed and a real CPU depth job produced a finite grid with the pinned checkpoint hash. See local `artifacts/streamlit-package-check.json`. This verifies clean package startup on this Windows machine; actual Community Cloud startup still needs to be observed after account deployment.

```powershell
$env:DEPTHFRAME_TEST_BASE_URL='http://127.0.0.1:8501'
$env:DEPTHFRAME_TEST_EDITOR_PATH='/workspace/'
powershell -ExecutionPolicy Bypass -File .\Test-DepthFrame.ps1
```

Sources: [Streamlit deployment](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy), [GitHub connection](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/connect-your-github-account), and the version-matched `st.App` documentation bundled with Streamlit 1.67.
