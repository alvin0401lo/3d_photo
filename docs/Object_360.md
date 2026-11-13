# Object 360°: orbit around a selected person

Open **http://127.0.0.1:8000**, then choose **Object 360°**. This workflow selects a subject from a photograph and uses Meshy's image-to-3D API to create a model you can orbit around. It is separate from Environment 360°, which looks around a panorama from one position.

## Try the controls without an account

Click **Try 3D person example**. Drag on the model to orbit through its front, sides and back. Use the arrow keys for 15° adjustments, Home / Reset object camera to return to the front, and the mouse wheel or a pinch gesture to zoom. Manual input pauses auto rotation. **Save object still** exports the current view; **Download GLB** saves the complete model.

This demo uses the pre-existing **Cesium Man** sample by Cesium, CC BY 4.0, from the Khronos glTF sample collection. The Cesium logo retains its separate trademark notice. The sample was not generated from the source screenshot or from your photo. It verifies the viewer, not the quality of AI person reconstruction.

## Configure Meshy privately

1. Create a Meshy account and an API key using [Meshy's official instructions](https://docs.meshy.ai/en/api/authentication). API usage requires Meshy API credits; see [current API pricing](https://docs.meshy.ai/en/api/pricing).
2. Copy `.env.example` to `.env` in the application folder, or add the following entries to an existing `.env` while preserving any OpenAI settings:

   ```dotenv
   MESHY_API_KEY=your_private_key_here
   MESHY_MODEL=meshy-7.1
   ```

3. Keep the real key private. Do not paste it into chat or commit `.env`. This is a separate key and account from OpenAI. The UI checks whether it is present automatically; presence does not establish authentication, credits, or model access.

The integration also accepts `meshy-6` and `meshy-6-lite` in `MESHY_MODEL`. Environment variables override `.env` entries. Requests use the official `api.meshy.ai` endpoint.

## Select and generate

1. Choose an existing ordinary photo or **Upload a reference**. This upload does not automatically run CPU depth inference. Use a clear photo of one person with the full body visible where possible.
2. Drag a box around the person/object. Adjust Left, Top, Width, and Height percentages with the numeric fields if needed. **Use whole photo** is useful when the image already contains one isolated subject.
3. Click **Confirm selection** and inspect **Confirmed input**. This is a rectangular crop, not precise automatic person segmentation. Exclude unrelated people and distracting objects. Only the confirmed crop is sent; original photo metadata is removed. Each crop must be at least 32 pixels wide and high; the submitted crop is reduced to at most 2048 pixels per side.
4. Choose pose guidance. The default omits a forced pose; A-pose and T-pose request those character poses from Meshy. The model may still interpret pose differently from the photo.
5. Check the consent box, then click **Generate object with Meshy**. This sends the crop to Meshy and uses your API credits. There is no paid request on screen opening or crop confirmation.
6. Keep DepthFrame running. When the task completes, the app saves the GLB and its input/manifest locally, then displays it in the orbit viewer. Closing the browser does not stop the worker. The source photo, any depth result, and any panorama are retained.

Changes to the selection clear consent and require confirmation before another generation. Previously generated models stay tied to their original confirmed crop; changing a crop does not regenerate a model automatically.

## Failures and cancellation

The app submits once and saves the provider task ID before polling. There is no automatic submission retry. If a task is interrupted after its ID is saved, **Resume existing Meshy task** reconnects to that task without starting a second generation. If submission disconnected before an ID was received, check your Meshy dashboard before creating another task.

Cancellation requests deletion of a known provider task when the worker observes it. Meshy may already have used credits. A worker shutdown or local timeout can leave remote processing active; inspect the provider dashboard. Generated model downloads are limited to 64 MB and must be self-contained GLB scenes; models requiring separate resources or unsupported compression are rejected with an error.

## Accuracy and validation

A single photo does not reveal the person's real sides/back. The reconstruction invents hidden surfaces, and face, hair, fingers, clothing, proportions and pose may differ. It is not an accurate body scan, identity guarantee, or rigged/animated avatar workflow. Multiple real views would provide stronger evidence for reconstruction; this release accepts one selected crop.

Backend tests mock Meshy responses to verify crop input, consent, task submission/polling, cancellation, resuming, error redaction, and model downloads. Browser checks verify real geometry orbiting using the credited sample and explicitly mocked form submission. **Live Meshy generation is unverified until a private key is configured and an actual result is reviewed.**

Sources: [Meshy image-to-3D API](https://docs.meshy.ai/en/api/image-to-3d), [Cesium Man source and notices](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CesiumMan).
