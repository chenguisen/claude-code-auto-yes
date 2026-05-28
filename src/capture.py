"""Screen region capture via mss."""

from __future__ import annotations

import numpy as np
import mss

from src.region_picker import Region


def capture_region(region: Region) -> np.ndarray:
    """Capture region as BGR numpy array (OpenCV convention)."""
    with mss.mss() as sct:
        shot = sct.grab(region.to_mss_monitor())
        # mss returns BGRA
        img = np.array(shot)
        bgr = img[:, :, :3]
        return bgr.copy()
