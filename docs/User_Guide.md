# DepthFrame AI — Local Application

## Open the installed application

Double-click **Start-DepthFrame.cmd** in the project folder. It starts the API and one CPU worker, then opens **http://127.0.0.1:8000**. Keep the launcher running; press **Ctrl+C** in its terminal, or double-click **Stop-DepthFrame.cmd**, to stop the services. If it is already running, the launcher reuses it.

The PowerShell equivalent is:

```powershell
cd C:\AAI\Project4Fun\3d_photo
powershell -ExecutionPolicy Bypass -File .\Start-DepthFrame.ps1
```

That bypass applies only to this invocation of the local script. The CMD launcher requires no PowerShell policy change.

## Create a 3D photo

For selecting a person/object and orbiting around a generated model, choose **Object 360°** instead and follow the [Object 360 guide](Object_360.md). It uses Meshy's separate API account and credits. The local **Try 3D person example** action demonstrates orbiting with a credited pre-existing model.

1. Choose **New photo**, drag a photo into the workspace, or select **Try example photo**.
2. Use a static JPG, PNG, or WebP, up to 15 MB, with each side between 32 and 4096 pixels. Actual file contents are checked. Animated files are rejected.
3. Watch the real processing stages. CPU inference runs in a separate worker. You may close the page and reopen the project while it processes, provided the launcher stays running.
4. Switch among **Original**, **Depth**, and **3D photo**. In Depth, light areas are nearer and dark areas are farther away.
5. Select **3D photo**, then click and drag (or touch and drag) to change the viewing angle. Release to keep that angle. Hover adds only gentle parallax. Focus the photo and use the arrow keys for small adjustments; Home or Reset camera restores the reference view. Manual dragging, arrow keys, and reset pause auto-orbit. Adjust Camera movement for a larger or smaller allowed angle range.
6. Click **Save** to preserve settings. Reopen the project through **Project library** or Recent photos.

Click the three-dot button beside the project name to rename or delete it. Deletion cancels active work and removes stored project files after the worker stops writing. Downloaded exports are independent files and remain on your computer.

## Export

- **Still image:** PNG of the current 3D camera view at the viewer's render resolution.
- **Orbit animation:** approximately five seconds, 1280×720, using a browser-supported video encoder. Chrome/Edge WebM is tested. Keep the tab visible. Frame rate depends on browser rendering/encoding resources; this is a real-time recording, not a frame-perfect offline render.
- **Depth map:** grayscale 16-bit PNG, normalized relative depth, with near = white. It is not a distance map in meters.
- **Textured depth mesh:** GLB with embedded image texture. This is a displaced photo surface, with no recovered backside or complete environment.
- **Project bundle:** ZIP containing the normalized photo, raw float depth, normalized depth, preview, binary browser grid, manifest, and saved settings. Save before exporting. The original upload/EXIF is excluded from this bundle.
- **Original photograph:** exact uploaded bytes. This file may still contain camera or location metadata.

The example's tested video, GLB, depth map, still, and ZIP are also in **artifacts/**. The original example and generated depth preview are in **examples/**. Photograph source/license information is in [CREDITS.md](../examples/CREDITS.md).

## What is private

The application listens only on loopback, uses local SQLite/files, and performs depth inference on the CPU. CPU depth, imported panoramas, and the captured example work locally. The optional **Environment 360° → Generate with OpenAI** action sends the selected normalized reference photo and prompt to OpenAI after you check consent, using your API credits. The backend reads the key from your private `.env`; it is not exposed through the UI or API responses. Internet access is also required for initial downloads and optional advisory/test-photo checks. Bundled fonts load locally.

## Full 360° environments

Choose **Environment 360° → Try 360° example** to look around a captured spherical landscape immediately. Drag horizontally through a complete turn and vertically toward the sky/ground. Arrow keys turn 15°; Home resets. Imported equirectangular panoramas require an exact 2:1 ratio, up to 8192 × 4096 pixels and 15 MB. Ordinary photo uploads keep the 4096-pixel limit.

To create imagined surroundings from an ordinary photo with your OpenAI API account, follow [Environment_360.md](Environment_360.md). It covers private key setup, consent, API credits, generation, downloads, and limitations. The app never repeats or mirrors an ordinary photo to present it as a generated panorama.

This is a single-user local application. Do not expose port 8000 through a tunnel, router, or public reverse proxy: account isolation, hosted quotas, and public operations belong to the separate Public V1 phase.

Uploads are in `storage/projects/`, metadata in `storage/depthframe.sqlite3`, and logs in `storage/logs/`. Stop the launcher before copying the complete storage folder for a simple local backup. Keep the database and project assets together. Restoring replaces the local workspace; retain the current copy first.

## Install on a clean Windows machine

Use Python 3.11 or 3.12 and Node.js 22.18 or newer compatible Node 22. Internet access and several GB of free disk space are needed for the runtime, dependencies, and model. The first setup downloads the pinned official Small checkpoint and verifies its SHA-256.

```powershell
cd C:\AAI\Project4Fun\3d_photo
powershell -ExecutionPolicy Bypass -File .\Setup-DepthFrame.ps1
```

If Python is not on PATH:

```powershell
powershell -ExecutionPolicy Bypass -File .\Setup-DepthFrame.ps1 -PythonPath 'C:\path\to\python.exe'
```

`npm.cmd` is used deliberately so PowerShell's npm.ps1 restriction does not block setup. After installation, normal photo processing works offline. The official source commit, checkpoint revision, and checksum are pinned in [models.lock.json](../models.lock.json).

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Cannot reach the service | Run Start-DepthFrame.cmd and inspect the terminal or storage/logs/api.log |
| CPU worker offline | Restart the launcher; inspect storage/logs/worker.log |
| Model missing/checksum mismatch | Rerun setup; remove only a known damaged checkpoint if download verification fails |
| A job fails | Read the recorded error and use Retry depth generation; original upload remains saved |
| A job was interrupted | Restart the worker, then retry the failed attempt; it will not silently remain running |
| Export disabled | Wait for a depth result and for the 3D texture/geometry to load |
| Video empty/unsupported | Keep the tab visible; try current Chrome or Edge; still/GLB exports remain available |
| Graphics unavailable | Use Original/Depth and downloads; retry in a WebGL2-capable browser |
| Settings conflict | Another tab saved this project. Reopen before applying new edits |
| Slow rendering | Select Draft or Balanced and reduce depth/camera movement |

Advanced settings: `DEPTHFRAME_CPU_THREADS` defaults to 4, `DEPTHFRAME_JOB_TIMEOUT` to 300 seconds, and `DEPTHFRAME_STORAGE` to the checkout's storage folder. Set the same storage override for both API and worker. One worker is enforced per storage directory.

## Limits of this release

The image supplies only the visible surfaces. Reflections, thin objects, hair, occlusion boundaries, and newly exposed areas can distort. Camera bounds intentionally remain small. The result is relative depth with arbitrary scale, not metric reconstruction.

Environment 360° supports looking in every direction from one fixed position. Optional OpenAI output invents unseen surroundings and can have seam/pole artifacts. Full walkable 3D reconstruction and public hosting are later phases. Physical-phone, Safari, and Firefox behavior is not established by Chromium desktop/emulated-width tests.
