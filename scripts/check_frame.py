"""Independent screenshot check: the colored photo must fit, without initial/resize cropping."""
import json
import sys

import numpy as np
from PIL import Image

image = np.asarray(Image.open(sys.argv[1]).convert("RGB"), dtype=np.int16)
aspect = float(sys.argv[2])
# The renderer background is neutral; the sample photo has colored pixels along all four sides.
colored = image.max(axis=2) - image.min(axis=2) > 20
y, x = np.where(colored)
assert len(x) > 100, "Photo not visible in canvas screenshot"
actual_width, actual_height = int(x.max() - x.min() + 1), int(y.max() - y.min() + 1)
height, width = image.shape[:2]
expected_width = min(width / 1.08, height / 1.08 * aspect)
expected_height = expected_width / aspect
assert abs(actual_width - expected_width) / width < .04, (actual_width, expected_width, width)
assert abs(actual_height - expected_height) / height < .04, (actual_height, expected_height, height)
assert x.min() > 0 and x.max() < width - 1 and y.min() > 0 and y.max() < height - 1, "Photo touches canvas boundary"
print(json.dumps({"canvas": [width, height], "photo_bounds": [actual_width, actual_height], "reference_framing": "passed"}))
