"""Mouse/keyboard injection for X11 and Wayland."""

from __future__ import annotations

import os
import shutil
import subprocess


class ClickError(RuntimeError):
    pass


def _backend_name() -> str:
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("ydotool"):
        return "ydotool"
    if shutil.which("xdotool") and os.environ.get("DISPLAY"):
        return "xdotool"
    if os.environ.get("DISPLAY"):
        return "pyautogui"
    return "none"


def click_absolute(x: int, y: int, *, restore_cursor: bool = True) -> str:
    """Click at screen coords; restore cursor when possible."""
    if shutil.which("xdotool") and os.environ.get("DISPLAY"):
        return _click_xdotool(x, y, restore_cursor=restore_cursor)
    backend = _backend_name()
    if backend == "ydotool":
        _click_ydotool(x, y)
        return "ydotool"
    if backend == "pyautogui":
        _click_pyautogui(x, y, restore_cursor=restore_cursor)
        return "pyautogui"
    raise ClickError("无可用点击后端，请安装: sudo apt install xdotool")


def _click_xdotool(x: int, y: int, *, restore_cursor: bool) -> str:
    orig = None
    if restore_cursor:
        try:
            out = subprocess.check_output(
                ["xdotool", "getmouselocation", "--shell"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            ox = oy = None
            for line in out.splitlines():
                if line.startswith("X="):
                    ox = int(line.split("=", 1)[1])
                elif line.startswith("Y="):
                    oy = int(line.split("=", 1)[1])
            if ox is not None and oy is not None:
                orig = (ox, oy)
        except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
            orig = None

    subprocess.run(
        ["xdotool", "mousemove", str(x), str(y), "click", "1"],
        check=True,
        capture_output=True,
    )
    if orig is not None:
        subprocess.run(
            ["xdotool", "mousemove", str(orig[0]), str(orig[1])],
            check=False,
            capture_output=True,
        )
    return "xdotool"


def _click_ydotool(x: int, y: int) -> None:
    subprocess.run(
        ["ydotool", "mousemove", "--absolute", str(x), str(y)],
        check=True,
        capture_output=True,
    )
    subprocess.run(["ydotool", "click", "0xC0"], check=True, capture_output=True)


def _click_pyautogui(x: int, y: int, *, restore_cursor: bool) -> None:
    import pyautogui

    pyautogui.FAILSAFE = False
    orig = pyautogui.position() if restore_cursor else None
    pyautogui.click(x, y, _pause=False)
    if restore_cursor and orig is not None:
        pyautogui.moveTo(orig.x, orig.y, duration=0)


def move_and_enter(x: int, y: int) -> str:
    """Move mouse to (x, y) and press Enter, preserving window focus."""
    if shutil.which("xdotool") and os.environ.get("DISPLAY"):
        # Save focused window so Enter goes to the right place
        orig = subprocess.run(
            ["xdotool", "getactivewindow"],
            capture_output=True, text=True,
        ).stdout.strip()

        subprocess.run(
            ["xdotool", "mousemove", str(x), str(y)],
            check=True, capture_output=True,
        )

        # Restore focus before pressing Enter
        if orig and orig.isdigit():
            subprocess.run(
                ["xdotool", "windowactivate", orig],
                check=False, capture_output=True,
            )

        subprocess.run(
            ["xdotool", "key", "Return"],
            check=True, capture_output=True,
        )
        return "xdotool_move_enter"
    raise ClickError("move+enter requires xdotool")


def press_yes_hotkey() -> str:
    if shutil.which("xdotool") and os.environ.get("DISPLAY"):
        subprocess.run(
            ["xdotool", "key", "1"],
            check=True,
            capture_output=True,
        )
        return "xdotool_key"
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("ydotool"):
        subprocess.run(["ydotool", "key", "1:1"], check=True, capture_output=True)
        return "ydotool_key"
    if os.environ.get("DISPLAY"):
        import pyautogui

        pyautogui.press("1")
        return "pyautogui_key"
    raise ClickError("无可用键盘后端")
