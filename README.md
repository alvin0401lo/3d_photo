# DepthFrame AI

Photo depth, environment panoramas, and selected-person/object 360° exploration, hosted through Streamlit.

## Deploy on Streamlit Community Cloud

Use **https://share.streamlit.io/** → **Create app**, then select:

| Setting | Value |
| --- | --- |
| Repository | `alvin0401lo/3d_photo` |
| Branch | `main` |
| Main file | `streamlit_app.py` |
| Python | `3.12` |

Keep the running app **private**: this is a single-user workspace. Configure provider keys in Streamlit **Secrets**, using `.streamlit/secrets.example.toml` as the template. No real credentials or uploaded photos are included in this repository. See [deployment details](docs/Streamlit_Deployment.md).

The first startup downloads the pinned Depth Anything V2 Small model. Node is not required by the hosted app; the compiled React/Three.js editor is included in `web_dist/`.

## Features

- Local CPU relative-depth estimation and an interactive depth photo with PNG/video/GLB/depth exports.
- Full 360° equirectangular panorama viewing, import, and a captured landscape example.
- Subject crop selection and Meshy image-to-3D integration, plus an orbitable credited sample character.
- Optional OpenAI panorama generation, with explicit external-processing consent.

Provider generation uses your API credits and requires the appropriate key. A single image does not establish the real hidden sides/back of a person. Captured panoramas and pre-existing 3D samples are labeled; they are not examples of live photo-to-3D generation. API contract mocks do not verify live provider quality.

Community Cloud storage is temporary: download important results before a restart. See [Object 360](docs/Object_360.md), [Environment 360](docs/Environment_360.md), and [third-party notices](THIRD_PARTY_NOTICES.md).

## Run locally

```sh
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

Open the URL printed by Streamlit. To rebuild the editor after frontend changes:

```sh
npm --prefix frontend ci
npm --prefix frontend run build
python scripts/prepare_streamlit.py
```

The original loopback FastAPI launcher remains available for local development. Streamlit uses a separate `streamlit_storage/` workspace. See [deployment details](docs/Streamlit_Deployment.md) for Windows launch commands and validation.
