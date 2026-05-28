"""Detect Claude Code permission prompt; track Yes click position each scan."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract
from pytesseract import Output, TesseractNotFoundError

for _tc in ("/usr/bin/tesseract", "/bin/tesseract"):
    if os.path.isfile(_tc):
        pytesseract.pytesseract.tesseract_cmd = _tc
        break

YES_LINE = re.compile(
    r"\d+\s*(?:yes|ves|yos|yea|y(?:e)?s?)\b|\d+\s*[yv][eo][sx]?\b",
    re.IGNORECASE,
)
NO_LINE = re.compile(r"\d+\s*no\b", re.IGNORECASE)
DIALOG_FOOTER = re.compile(
    r"tell\s+claude\s+what\s+to\s+do|esc\s+to\s+cancel",
    re.IGNORECASE,
)

BLUE_HSV_LOWER = np.array([90, 60, 60])
BLUE_HSV_UPPER = np.array([130, 255, 255])

# Claude UI: Yes 条在 No 条正上方，约 35~55 像素（随分辨率略有变化）
YES_ABOVE_NO_PX = 42
OCR_SCALE = 2.5


@dataclass
class DetectionResult:
    local_x: int
    local_y: int
    method: str
    ocr_text: str


@dataclass
class _Box:
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2

    @property
    def top(self) -> int:
        return self.y


def _auto_threshold(scaled: np.ndarray) -> np.ndarray:
    """Apply Otsu threshold, auto-inverting if the image is light-on-dark."""
    _, thresh = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # If fewer than 15% white pixels, the image likely has light text on dark bg
    white_ratio = (thresh == 255).sum() / thresh.size
    if white_ratio < 0.15:
        _, thresh = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return thresh


def _preprocess_for_ocr(bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(
        gray, None, fx=OCR_SCALE, fy=OCR_SCALE, interpolation=cv2.INTER_CUBIC
    )
    return _auto_threshold(scaled)


def _ocr_text(bgr: np.ndarray) -> str | None:
    """OCR with auto-threshold; falls back to raw scaled gray if result is empty."""
    try:
        text = pytesseract.image_to_string(
            _preprocess_for_ocr(bgr), config="--psm 6"
        ).strip()
        if text:
            return text
        # Fallback: try raw grayscale (no thresholding)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        scaled = cv2.resize(gray, None, fx=OCR_SCALE, fy=OCR_SCALE, interpolation=cv2.INTER_CUBIC)
        text = pytesseract.image_to_string(scaled, config="--psm 6").strip()
        return text or None
    except TesseractNotFoundError:
        return None


def _ocr_word_boxes(image: np.ndarray, y_offset: int) -> list[tuple[str, _Box]]:
    try:
        data = pytesseract.image_to_data(
            _preprocess_for_ocr(image),
            output_type=Output.DICT,
            config="--psm 6",
        )
    except TesseractNotFoundError:
        return []

    out: list[tuple[str, _Box]] = []
    inv = 1.0 / OCR_SCALE
    for i in range(len(data["text"])):
        word = (data["text"][i] or "").strip()
        if not word:
            continue
        conf = int(data["conf"][i]) if str(data["conf"][i]).isdigit() else -1
        if conf >= 0 and conf < 5:
            continue
        x = int(data["left"][i] * inv)
        y = int(data["top"][i] * inv) + y_offset
        w = max(1, int(data["width"][i] * inv))
        h = max(1, int(data["height"][i] * inv))
        out.append((word, _Box(x, y, w, h)))
    # If word boxes are empty, retry with raw grayscale
    if not out:
        try:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            scaled = cv2.resize(gray, None, fx=OCR_SCALE, fy=OCR_SCALE, interpolation=cv2.INTER_CUBIC)
            data = pytesseract.image_to_data(scaled, output_type=Output.DICT, config="--psm 6")
            for i in range(len(data["text"])):
                word = (data["text"][i] or "").strip()
                if not word:
                    continue
                conf = int(data["conf"][i]) if str(data["conf"][i]).isdigit() else -1
                if conf >= 0 and conf < 5:
                    continue
                x = int(data["left"][i] * inv)
                y = int(data["top"][i] * inv) + y_offset
                w = max(1, int(data["width"][i] * inv))
                h = max(1, int(data["height"][i] * inv))
                out.append((word, _Box(x, y, w, h)))
        except TesseractNotFoundError:
            pass
    return out


def _merge_boxes(a: _Box, b: _Box) -> _Box:
    x0 = min(a.x, b.x)
    y0 = min(a.y, b.y)
    x1 = max(a.x + a.w, b.x + b.w)
    y1 = max(a.y + a.h, b.y + b.h)
    return _Box(x0, y0, x1 - x0, y1 - y0)


def _find_no_box(words: list[tuple[str, _Box]]) -> _Box | None:
    for i, (w, box) in enumerate(words):
        if re.match(r"\d+", w, re.I) and i + 1 < len(words):
            w2, b2 = words[i + 1]
            if re.match(r"no\b", w2, re.I):
                return _merge_boxes(box, b2)
        if re.match(r"\d+\s*no\b", w, re.I):
            return box
    return None


def _find_yes_box(words: list[tuple[str, _Box]]) -> _Box | None:
    for i, (w, box) in enumerate(words):
        if re.match(r"(?:\d+\s*)?(?:[YyVv]e[sz]|[Yy]os|yea)\b", w):
            return box
        if re.match(r"\d+", w) and i + 1 < len(words):
            w2, b2 = words[i + 1]
            if re.match(r"[YyVv]e[sxz]?\b|yea\b", w2):
                return _merge_boxes(box, b2)
    return None


def _click_above_no(no_box: _Box) -> tuple[int, int]:
    """Yes 在 No 正上方：每次根据 No 的位置动态算 Yes 点击点。"""
    return no_box.cx, no_box.top - YES_ABOVE_NO_PX


def _find_yes_blue_button(work: np.ndarray, y_offset: int, *, above_y: int | None) -> tuple[int, int] | None:
    hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, BLUE_HSV_LOWER, BLUE_HSV_UPPER)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    roi_w = work.shape[1]
    best: tuple[int, int, int, int, int] | None = None

    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw * bh < 300 or bw < roi_w * 0.30 or bw / max(bh, 1) < 1.5:
            continue
        cy = y_offset + y + bh // 2
        if above_y is not None and cy >= above_y:
            continue
        score = y
        if best is None or score < best[0]:
            best = (score, x, y, bw, bh, cy)

    if best is None:
        return None
    _, x, y, bw, bh, _ = best
    return x + bw // 2, y_offset + y + bh // 2


def _scan_yes_no(text: str) -> tuple[bool, bool]:
    return bool(YES_LINE.search(text)), bool(NO_LINE.search(text))


def _is_permission_dialog(text: str) -> bool:
    if not NO_LINE.search(text):
        return False
    return bool(DIALOG_FOOTER.search(text))


def find_yes_click_point(
    bgr: np.ndarray,
    *,
    require_context: bool = True,
    verbose: bool = False,
    on_log: Callable[[str], None] | None = None,
) -> DetectionResult | None:
    """
    点击位置不是固定的：每次截屏后重新 OCR 跟踪。
    优先级：Yes 文字框 > No 上方偏移 > 蓝色按钮（且在 No 上方）
    """
    def log(msg: str) -> None:
        if verbose:
            if on_log:
                on_log(msg)
            else:
                print(msg)

    text = _ocr_text(bgr) or ""
    if not text.strip():
        return None

    has_yes, has_no = _scan_yes_no(text)
    dialog = _is_permission_dialog(text)

    if not has_no:
        return None
    if not dialog and not (has_yes and has_no):
        return None

    words = _ocr_word_boxes(bgr, 0)
    yes_box = _find_yes_box(words)
    no_box = _find_no_box(words)

    if verbose:
        log(f"[detect] Yes={has_yes} No={has_no} dialog={dialog}")
        if yes_box:
            log(f"[track] Yes box center=({yes_box.cx},{yes_box.cy})")
        if no_box:
            log(f"[track] No  box center=({no_box.cx},{no_box.cy})")

    if yes_box is not None:
        return DetectionResult(
            local_x=yes_box.cx,
            local_y=yes_box.cy,
            method="track_yes_text",
            ocr_text=text,
        )

    if no_box is not None:
        cx, cy = _click_above_no(no_box)
        if verbose:
            log(f"[track] click above No -> ({cx},{cy})")
        return DetectionResult(
            local_x=cx,
            local_y=cy,
            method="track_above_no",
            ocr_text=text,
        )

    no_top = no_box.top if no_box else None
    point = _find_yes_blue_button(bgr, 0, above_y=no_top)
    if point is not None:
        return DetectionResult(
            local_x=point[0],
            local_y=point[1],
            method="track_blue_btn",
            ocr_text=text,
        )

    return None
