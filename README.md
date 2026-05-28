# Claude Code Auto Yes

Claude Code 频繁弹出 `Allow bash`、`Allow file operations` 等权限确认对话框，
每个都必须手动点击 **Yes** 才能继续。在长时间或批处理任务中，这会严重打断工作流。

这个工具通过 **OCR 实时监测屏幕区域**，自动检测并点击 Yes 按钮，
让你不用守在电脑前频繁点击确认。

## How It Works

1. Pick a screen region around the Claude Code permission dialog
2. The app OCR-scans that region every 5 seconds
3. When it detects `Yes` (and optionally `No` + confirmation footer), it clicks Yes
4. Supports both mouse click and keyboard shortcut (`1`)

```
                  ┌──────────────────────┐
Monitor loop ───→ │ Capture region (mss)  │
                  └────────┬─────────────┘
                           ↓
                  ┌──────────────────────┐
                  │ OCR (tesseract)       │
                  │ Find Yes / No buttons │
                  └────────┬─────────────┘
                           ↓
                  ┌──────────────────────┐
                  │ Click Yes or press 1  │
                  └──────────────────────┘
```

## Requirements

- **Linux** with X11 or [XWayland](https://wayland.freedesktop.org/xserver.html)
- Python 3.10+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) — `sudo apt install tesseract-ocr`
- [xdotool](https://github.com/jordansissel/xdotool) — `sudo apt install xdotool` (for mouse clicks)
- A [Claude Code](https://claude.ai) session with permission dialogs

## Quick Start

```bash
# Install system dependencies
sudo apt install tesseract-ocr xdotool python3-tk

# Clone & install
git clone https://github.com/yourname/claude-code-auto-yes.git
cd claude-code-auto-yes
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Launch
python -m src.app
# or: bash run.sh
```

1. Click **Pick Region** — drag a blue box tightly around the Claude permission dialog
   (include the "1 Yes" and "2 No" / "2 Yes" and "3 No" buttons)
2. Click **Start** — the monitor begins scanning every 5 seconds
3. When a permission dialog appears, the app auto-clicks Yes

> **Tip**: Enable **Dry run** first to verify detection in the log before allowing actual clicks.

## Options

| Option | Default | Description |
|--------|---------|-------------|
| Dry run | off | Log detections without clicking |
| Verbose log | off | Show raw OCR text for debugging |
| Keyboard only | off | Send `1` key instead of mouse click |
| Restore cursor | on | Return mouse to original position after click |

## Command Line

```bash
python -m src.monitor --help
python -m src.monitor --pick-region
python -m src.monitor --dry-run --verbose
python -m src.monitor
```

## Detection Logic

The detector uses a multi-strategy approach:

1. **Yes text** — OCR finds a "Yes" word → click its center
2. **Above No** — OCR finds "No" but not "Yes" → click ~42px above No (where Yes should be)
3. **Blue button** — Find a blue UI element above the No row → click its center

The click point is **recomputed every scan** — it tracks the dialog even if it moves
or if the Claude window is repositioned.

Detection works with both the classic `1 Yes / 2 No` and newer `2 Yes / 3 No` formats.

## Multi-Monitor Support

On X11/XWayland, the region picker covers the entire virtual desktop.
Select a region on any connected monitor — coordinates are saved in virtual
desktop space and work correctly with the screen capture engine.

## Project Structure

```
claude-code-auto-yes/
├── src/
│   ├── app.py              Qt6 GUI + monitor worker thread
│   ├── monitor.py          Main monitoring loop
│   ├── detector.py         OCR-based button detection
│   ├── capture.py          Screen region capture (mss)
│   ├── clicker.py          Mouse/keyboard injection
│   ├── region_picker.py    Qt6 fullscreen overlay picker
│   ├── config_paths.py     File path helpers
│   ├── __init__.py         Package marker
│   └── __main__.py         Entry point
├── scripts/
│   └── diagnose.py         One-shot test and debug tool
├── config/
│   └── region.json         Saved region (auto-generated)
├── pyproject.toml           Python package metadata
├── requirements.txt         Dependencies
├── run.sh                   Quick launcher
└── README.md
```

## Troubleshooting

```bash
# Install required system tools
sudo apt install tesseract-ocr xdotool

# Test detection with current region
source .venv/bin/activate
python scripts/diagnose.py
python scripts/diagnose.py --click   # actually click

# Test with a saved screenshot
python scripts/diagnose.py --save-debug
# Check config/last_click_debug.png for the detected position

# Kill a stuck background process
pkill -f src.app

# Reset region config
rm config/region.json
```

## Diagnostics

The `diagnose.py` script captures one frame and reports what it finds:

```
$ python scripts/diagnose.py
region box (fixed): x=1344 y=606 w=577 h=473
backend: xdotool  xdotool: /usr/bin/xdotool
[detect] Yes=True No=True dialog=True
[track] Yes box center=(48,190)
detect: local_x=48 local_y=190 method=track_yes_text
=> This scan would click screen (1392, 796) via track_yes_text
```

## Development

```bash
git clone ...
cd claude-code-auto-yes
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Testing changes

The codebase has no automated tests yet. Test manually:

1. Run `python scripts/diagnose.py` with a dialog visible
2. Run the GUI with `python -m src.app`
3. Use **Dry run** mode to verify detection before enabling clicks

## License

MIT
