"""Main monitoring loop: capture region, detect Yes, click."""

from __future__ import annotations

import argparse
import sys
import threading
import time
from collections.abc import Callable

from src.capture import capture_region
from src.clicker import ClickError, _backend_name, click_absolute, press_yes_hotkey
from src.detector import find_yes_click_point
from src.region_picker import (
    Region,
    load_region,
    parse_region_arg,
    pick_and_save_region,
    save_region,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="监测截图区域，检测到 Claude Code 权限弹窗 Yes 后自动点击",
    )
    parser.add_argument(
        "--pick-region",
        action="store_true",
        help="交互框选监测区域并保存到 config/region.json",
    )
    parser.add_argument(
        "--set-region",
        metavar="X,Y,W,H",
        help="手动设置区域并保存，例如 1200,600,400,200",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="截屏间隔（秒），默认 5",
    )
    parser.add_argument(
        "--no-context-check",
        action="store_true",
        help="跳过 Allow/bash 上下文检查（调试用）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印检测到的坐标，不执行点击",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="打印 OCR 文本",
    )
    parser.add_argument(
        "--confirm-frames",
        type=int,
        default=2,
        help="连续检测到 Yes 的帧数后才点击，默认 2",
    )
    parser.add_argument(
        "--cooldown",
        type=float,
        default=1.5,
        help="点击后冷却时间（秒），默认 1.5",
    )
    return parser.parse_args(argv)


def run_monitor(
    region: Region,
    *,
    interval: float = 5.0,
    require_context: bool = True,
    dry_run: bool = False,
    verbose: bool = False,
    confirm_frames: int = 1,
    cooldown: float = 2.0,
    stop_event: threading.Event | None = None,
    on_message: Callable[[str], None] | None = None,
    keyboard_only: bool = False,
    restore_cursor: bool = True,
) -> None:
    def log(msg: str) -> None:
        if on_message:
            on_message(msg)
        else:
            print(msg)

    backend = _backend_name()
    if backend == "none" and not dry_run:
        log("警告: 未检测到点击后端，将只检测不点击")

    if not on_message:
        log(
            f"开始监测区域: x={region.x}, y={region.y}, "
            f"{region.width}x{region.height}, 间隔={interval}s"
        )
        if not dry_run and backend != "none":
            log(f"点击后端: {backend}")

    last_click_time = 0.0
    streak = 0
    last_point: tuple[int, int] | None = None

    def sleep_interval() -> bool:
        """Sleep up to interval seconds. Returns True if stop requested."""
        if stop_event is None:
            time.sleep(interval)
            return False
        return bool(stop_event.wait(interval))

    try:
        while True:
            if stop_event and stop_event.is_set():
                break

            now = time.monotonic()
            if now - last_click_time < cooldown:
                if sleep_interval():
                    break
                continue

            bgr = capture_region(region)
            result = find_yes_click_point(
                bgr,
                require_context=require_context,
                verbose=verbose,
                on_log=on_message,
            )

            if result is None:
                log("scan: idle")
                streak = 0
                last_point = None
                if sleep_interval():
                    break
                continue

            abs_x = region.x + result.local_x
            abs_y = region.y + result.local_y
            point = (abs_x, abs_y)

            if last_point == point:
                streak += 1
            else:
                streak = 1
                last_point = point

            if streak < confirm_frames:
                if sleep_interval():
                    break
                continue

            log(
                f"Found ({result.method}) region=({result.local_x},{result.local_y}) "
                f"-> screen=({abs_x},{abs_y}) [tracked this scan]"
            )

            if dry_run:
                streak = 0
                last_click_time = now
                if sleep_interval():
                    break
                continue

            clicked = False
            if not keyboard_only:
                try:
                    used = click_absolute(
                        abs_x, abs_y, restore_cursor=restore_cursor
                    )
                    log(f"OK: click ({abs_x},{abs_y}) via {used}")
                    clicked = True
                except ClickError as exc:
                    log(f"click failed: {exc}")
                except Exception as exc:
                    log(f"click error: {exc}")

            if keyboard_only or not clicked:
                try:
                    used = press_yes_hotkey()
                    log(f"OK: key 1 via {used}")
                    clicked = True
                except Exception as exc:
                    log(f"key 1 failed: {exc}")

            if not clicked:
                log("ERROR: all click methods failed; install: sudo apt install xdotool")

            streak = 0
            last_point = None
            last_click_time = time.monotonic()
            if sleep_interval():
                break

    except KeyboardInterrupt:
        if not on_message:
            print("\n已停止监测")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.pick_region:
        pick_and_save_region()
        return 0

    if args.set_region:
        try:
            region = parse_region_arg(args.set_region)
        except ValueError as exc:
            print(f"区域参数错误: {exc}", file=sys.stderr)
            return 1
        save_region(region)
        print(
            f"区域已保存: x={region.x}, y={region.y}, "
            f"width={region.width}, height={region.height}"
        )
        return 0

    region = load_region()
    if region is None:
        print("未找到区域配置，请先框选监测区域…")
        region = pick_and_save_region()
        if region is None:
            print("未设置监测区域，退出")
            return 1

    run_monitor(
        region,
        interval=args.interval,
        require_context=not args.no_context_check,
        dry_run=args.dry_run,
        verbose=args.verbose,
        confirm_frames=args.confirm_frames,
        cooldown=args.cooldown,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
