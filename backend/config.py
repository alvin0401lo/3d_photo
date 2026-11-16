"""Read only the documented server settings; never expose credentials through API responses."""
import os
from .store import ROOT

IMAGE_MODELS = {"gpt-image-2", "gpt-image-2-2026-04-21", "gpt-image-2.5-sunburst", "gpt-image-2.5-sunburst-2026-09-08", "gpt-image-2.5-flare", "gpt-image-2.5-flare-2026-09-08"}


def private_settings(keys):
    values = {}
    path = ROOT / ".env"
    if path.exists():
        if path.stat().st_size > 65536:
            raise ValueError("The local configuration file is too large.")
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in keys:
                values[key.strip()] = value.strip().strip('"').strip("'")
    for key in keys:
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def openai_config():
    values = private_settings(("OPENAI_API_KEY", "OPENAI_IMAGE_MODEL", "OPENAI_IMAGE_TIMEOUT"))
    model = values.get("OPENAI_IMAGE_MODEL") or "gpt-image-2.5-sunburst"
    if model not in IMAGE_MODELS:
        raise ValueError("Choose a configured image model that supports 2:1 output dimensions. See .env.example.")
    try:
        timeout = max(30, min(600, int(values.get("OPENAI_IMAGE_TIMEOUT", "300"))))
    except ValueError:
        timeout = 300
    return {"api_key": values.get("OPENAI_API_KEY", "").strip(), "model": model, "timeout": timeout}


def tripo_config():
    values = private_settings(("TRIPO_API_KEY", "TRIPO_MODEL"))
    model = values.get("TRIPO_MODEL") or "v3.1-20260211"
    if model != "v3.1-20260211":
        raise ValueError("Choose the supported Tripo image-to-3D model in .env.example.")
    return {"api_key": values.get("TRIPO_API_KEY", "").strip(), "model": model}
