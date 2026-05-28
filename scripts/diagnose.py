#!/usr/bin/env python3
"""One-shot test: capture region, detect, report; optional debug image."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.capture import capture_region
from src.clicker import _backend_name, click_absolute
from src.detector import find_yes_click_point
from src.region_picker import load_region


def main() -> int:
    r = load_region()
    if r is None:
        print("No region.json - run: python -m src.app -> Pick region")
        return 1

    print(f"region box (fixed): x={r.x} y={r.y} w={r.width} h={r.height}")
    print(f"click point: RE-COMPUTED every scan (not fixed)")
    print(f"backend: {_backend_name()}  xdotool: {shutil.which('xdotool')}")

    bgr = capture_region(r)
    res = find_yes_click_point(bgr, verbose=True)
    print("detect:", res)

    if res is None:
        print("\n=> No dialog now. Trigger Allow/bash in Claude, run again.")
        return 0

    ax, ay = r.x + res.local_x, r.y + res.local_y
    print(f"\n=> This scan would click screen ({ax}, {ay}) via {res.method}")

    if "--save-debug" in sys.argv:
        vis = bgr.copy()
        cv2.circle(vis, (res.local_x, res.local_y), 12, (0, 255, 0), 2)
        cv2.drawMarker(
            vis, (res.local_x, res.local_y), (0, 255, 0),
            cv2.MARKER_CROSS, 24, 2,
        )
        out = ROOT / "config" / "last_click_debug.png"
        out.parent.mkdir(exist_ok=True)
        cv2.imwrite(str(out), vis)
        print(f"Saved marker image: {out}")

    if "--click" in sys.argv:
        used = click_absolute(ax, ay, restore_cursor=True)
        print(f"clicked via {used}")
    else:
        print("Add --click to click  |  --save-debug to save marker PNG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
