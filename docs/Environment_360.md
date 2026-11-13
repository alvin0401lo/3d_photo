# Environment 360°

Open **http://127.0.0.1:8000**, choose **Environment 360°**, then **Try 360° example**. The example is the captured CC0 Kiara 1 Dawn panorama by Greg Zaal / Poly Haven. It works locally without an API key.

Drag to look around the complete sphere. Two viewport-width horizontal swipes make a full turn; there is no horizontal angle limit. Drag vertically to look up/down, use arrow keys to turn in 15° steps, or Home / Reset camera to return to the start. Manual input pauses automatic rotation. Zoom and auto look-around settings can be saved; the current manually selected direction resets when reopening. The degree readout is relative to the image's starting direction, not geographic north.

**Export → Still image** saves the current view. **360° panorama** saves the complete 2:1 equirectangular image for another compatible viewer. Generated projects also expose a JSON generation manifest. CPU photo depth/video/GLB exports remain in the 3D photo mode.

## Generate an environment from one ordinary photo

1. Copy `.env.example` to `.env` in `C:\AAI\Project4Fun\3d_photo`. Enter your OpenAI API key privately after `OPENAI_API_KEY=`. Keep `.env` out of chat and version control. API billing is separate from a ChatGPT subscription.
2. Leave `OPENAI_IMAGE_MODEL=gpt-image-2.5-sunburst`, or choose another supported 2:1-capable model listed in `backend/config.py` that your API project can access. Older models limited to 3:2 output are not supported by this path. An optional `OPENAI_IMAGE_TIMEOUT` is clamped to 30–600 seconds. No custom base URL is used; requests go to the official OpenAI endpoint.
3. In **Environment 360°**, choose an existing reference photograph or **Upload reference photo**. Ordinary photos use the existing 15 MB / 4096-pixel-per-side limit.
4. Optionally describe the surroundings and choose generation quality. Check the consent box to send the selected photo and use your API credits, then click **Generate with OpenAI**. The key stays on the Python backend. Only the normalized reference JPEG and prompt are sent; original EXIF is removed.
5. Keep DepthFrame running. The job is queued durably, then the worker makes one image-edit request with a 2048×1024 target. This can take several minutes. Closing the browser does not stop processing.
6. When complete, click **Open 360° environment**. The result is stored in the photo project; the original photo and any depth result are retained. Inspect the forward view, side/back views, joining seam, sky/ceiling, and ground/floor before using the result.

The app rechecks `.env` on configuration polls and job execution; changing the file does not require a restart. An environment variable with the same name takes precedence. Configuration readiness only means a key is present; it does not prove authentication, billing, model access, or generation success.

AI image generation does not guarantee a mathematically seamless panorama or faithful unseen geometry. The app rejects invalid/non-2:1 image responses. A correctly shaped image may still contain visible seams, pole artifacts, duplicate objects, or inconsistent structures. This is an experimental fixed-viewpoint spherical environment, not a walkable scene or a recovery of what was really behind the camera.

There are no automatic retries. A timeout, disconnect, local cancellation, or worker shutdown may still consume credits if OpenAI already received the request. Inspect your API account before manually retrying. Provider error messages are redacted; the UI reports authentication, access, quota, timeout, or output validation failures.

## Import a panorama

Choose **Import panorama** for a JPEG, PNG, or WebP equirectangular image with an exact 2:1 ratio, 32–8192 pixels per side, and a maximum of 15 MB. A normal photo cropped to 2:1 is not a spherical panorama; use the AI workflow for ordinary photos. Imports open directly without CPU depth inference or an external API call.

## Sources and verification limits

- [OpenAI image generation guide](https://developers.openai.com/api/docs/guides/image-generation)
- [OpenAI image-edit API reference](https://developers.openai.com/api/reference/resources/images/methods/edit)
- [Poly Haven captured example](https://polyhaven.com/a/kiara_1_dawn)

API contract tests use explicit mock responses and never substitute a fake result in the application. The captured example verifies viewer behavior, not ordinary-photo AI generation quality. A live OpenAI generation and visual quality review require a configured private key.
