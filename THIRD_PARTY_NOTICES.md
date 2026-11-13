# Third-party notices

DepthFrame's model download script obtains the official Depth Anything V2 code at the commit pinned in models.lock.json and the Small checkpoint at the pinned model revision. Its upstream license/README are retained in .vendor/depth-anything-v2 after setup. The **Small** model is Apache 2.0; other model sizes have different terms and are not included.

- Depth Anything V2: https://github.com/DepthAnything/Depth-Anything-V2
- Small checkpoint: https://huggingface.co/depth-anything/Depth-Anything-V2-Small
- PyTorch/torchvision: https://github.com/pytorch/pytorch and https://github.com/pytorch/vision (retain their installed distribution notices)
- React: https://github.com/facebook/react (MIT)
- Three.js: https://github.com/mrdoob/three.js (MIT)
- React Three Fiber: https://github.com/pmndrs/react-three-fiber (MIT)
- FastAPI: https://github.com/fastapi/fastapi (MIT)
- Starlette: https://github.com/Kludex/starlette (BSD-3-Clause)
- Inter: https://github.com/rsms/inter (SIL Open Font License 1.1; bundled fontsource distribution retains its license)
- Lucide icons: https://github.com/lucide-icons/lucide (ISC)
- Other installed libraries retain their distribution licenses in the Python/npm environments. See the exact frontend lockfile and package metadata for the full dependency set.

The bundled landscape and optional regression photographs are stock demonstration inputs, used under the Pexels license. See examples/CREDITS.md and artifacts/photo-suite/report.json for their source pages. They are not user uploads, and their depth predictions are not ground-truth geometry.

No SEVA weights/code are included in this local release. Its published non-commercial terms are not assumed to authorize a commercial future release.

The captured 360° example is **Kiara 1 Dawn** by **Greg Zaal**, distributed by [Poly Haven](https://polyhaven.com/a/kiara_1_dawn) under CC0. The bundled 4096×2048 JPEG is resized from its tonemapped equirectangular source. `examples/kiara-panorama.json` records its source and checksum. This is a captured panorama, not a demonstration of AI conversion from an ordinary photo.

Optional OpenAI image generation is a remote paid API service under the user's account. No API key is bundled. Model output is AI inferred and is not factual scene reconstruction.

The Object 360° demo is **Cesium Man**, copyright 2017 Cesium, CC BY 4.0, obtained from the [Khronos glTF sample collection](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CesiumMan). The Cesium logo retains the separate [Cesium trademark notice](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/main/LICENSES/LicenseRef-LegalMark-Cesium.txt). The screenshot is converted from the first frame of the source GIF for a static reference. The GLB is preserved unchanged. It is a pre-existing sample, not a photo-generated person. Checksum/source details are in examples/cesium-man.json.

Meshy is an optional remote paid image-to-3D API under the user's account. No Meshy key is bundled. The app sends the confirmed crop only when generation is explicitly requested with consent. Generated geometry can differ from the real person.
