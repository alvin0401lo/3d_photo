"""Measure actual rendered-pixel change for the camera interaction regression."""
import json
import sys
import numpy as np
from PIL import Image

first = np.asarray(Image.open(sys.argv[1]).convert("RGB"), dtype=np.float32)
second = np.asarray(Image.open(sys.argv[2]).convert("RGB"), dtype=np.float32)
assert first.shape == second.shape, (first.shape, second.shape)
difference = np.abs(first - second)
print(json.dumps({"mean_difference": float(difference.mean()), "changed_fraction": float((difference.max(axis=2) > 10).mean())}))
