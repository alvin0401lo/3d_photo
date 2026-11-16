# Object 360°: orbit around a selected person

Open **http://127.0.0.1:8000**, then choose **Object 360°**. Draw a box around a person or object, confirm the crop, and generate a textured 3D model with Tripo. Drag the result to orbit around it. This is separate from Environment 360°, which looks around a panorama from one position.

## Try the controls without an account

Click **Try 3D person example**. Drag on the model to orbit through its front, sides and back. Use the arrow keys for 15° adjustments, Home / Reset object camera to return to the front, and the mouse wheel or a pinch gesture to zoom. Manual input pauses auto rotation. **Save object still** exports the current view; **Download GLB** saves the complete model.

This demo uses the pre-existing **Cesium Man** sample by Cesium, CC BY 4.0, from the Khronos glTF sample collection. The Cesium logo retains its separate trademark notice. The sample was not generated from the source screenshot or from your photo. It verifies the viewer, not the quality of AI person reconstruction.

## Configure Tripo privately

1. Create a Tripo account and API key using [Tripo's authentication guide](https://developers.tripo3d.ai/en/docs/authentication). Image-to-3D generation uses credits from your Tripo account; check the [current pricing](https://developers.tripo3d.ai/en/docs/billing).
2. Copy .env.example to .env in the application folder, or add these entries to your existing .env while preserving any OpenAI settings:

       TRIPO_API_KEY=your_private_key_here
       TRIPO_MODEL=v3.1-20260211

3. Keep the real key private. Do not paste it into chat or commit .env. The Tripo key and credits are separate from OpenAI. The UI checks whether a key is present; this does not prove authentication, credits, or model access.

For Streamlit Community Cloud, add TRIPO_API_KEY and TRIPO_MODEL under **App settings → Secrets** using .streamlit/secrets.example.toml as the format. Do not put a real key in GitHub.

## Select and generate

1. Choose an existing ordinary photo or **Upload a reference**. Use a clear photo of one person with the full body visible where possible.
2. Drag a box around the person/object. Adjust Left, Top, Width, and Height percentages with the numeric fields if needed. **Use whole photo** is useful when the image already contains one isolated subject.
3. Click **Confirm selection** and inspect **Confirmed input**. This is a rectangular crop, not precise automatic person segmentation. Exclude unrelated people and distracting objects. Only the confirmed crop is sent after consent; original photo metadata is removed. Each crop must be at least 32 pixels wide and high and is reduced to at most 2048 pixels per side.
4. Choose automatic model orientation or align the model to the input view.
5. Check the consent box, then click **Generate object with Tripo**. The confirmed crop is uploaded to Tripo and the image-to-3D task uses Tripo API credits. No paid generation request is made when opening the screen or confirming a crop.
6. Keep DepthFrame running. When the task completes, the app saves the GLB and its input/manifest locally, then displays it in the orbit viewer. Closing the browser does not stop the worker.

Changes to the selection clear consent and require confirmation before another generation. Previously generated models stay tied to their original confirmed crop; changing a crop does not regenerate a model automatically.

## Failures and cancellation

The app uploads the crop and submits one generation request, saving the returned Tripo task ID before polling. It does not automatically retry a generation request. If submission disconnects before a task ID is received, check your Tripo dashboard before starting another task. If a task ID was saved, **Resume existing Tripo task** checks that same task instead of generating another model.

Cancellation stops this app's polling and local processing. It does not send a provider cancellation request, so Tripo may continue the task and charge credits if it succeeds. Check your Tripo dashboard. A worker shutdown or timeout can leave remote processing active. Generated downloads are limited to 64 MB and must be self-contained GLB scenes; models requiring separate resources or unsupported compression are rejected.

Previously saved Meshy tasks cannot be resumed through the Tripo integration. Completed models already saved in a project remain available.

If a completed Tripo task previously failed with an unsupported download address, update the app and click **Resume existing Tripo task**. Downloads support Tripo CDN and regional `*.data.tripo3d.com` / `*.data.tripo3d.ai` addresses, with each redirect checked before fetching. Resume queries the saved task and downloads its model without creating another generation task.

## Accuracy and validation

A single photo does not reveal the person's real sides/back. The reconstruction infers hidden surfaces, and face, hair, fingers, clothing, proportions and pose may differ. It is not an accurate body scan, identity guarantee, or rigged/animated avatar workflow. Multiple real views would provide stronger evidence for reconstruction; this workflow accepts one selected crop.

Automated tests mock Tripo responses to verify the crop upload, consent, task submission/polling, cancellation, resume without a second generation request, error redaction and model downloads. Browser checks verify real geometry orbiting using the credited sample and explicitly mocked form submission. **Live Tripo generation remains unverified until a private key is configured and an actual result is reviewed.**

Sources: [Tripo image upload API](https://developers.tripo3d.ai/en/docs/files), [Tripo image-to-3D API](https://developers.tripo3d.ai/en/docs/generation-image-to-model/standard), [Tripo task query API](https://developers.tripo3d.ai/en/docs/task-query), [Cesium Man source and notices](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CesiumMan).
