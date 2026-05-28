#!/usr/bin/env bash
# Install system dependencies for claude_code_auto
set -euo pipefail

echo "Installing tesseract-ocr and CJK fonts (for GUI)..."
sudo apt-get update -qq
sudo apt-get install -y tesseract-ocr fonts-noto-cjk xdotool

if [ -n "${WAYLAND_DISPLAY:-}" ]; then
  echo "Wayland detected. Installing ydotool (optional, for mouse clicks)..."
  sudo apt-get install -y ydotool || echo "ydotool install failed; you may need it for Wayland clicks"
  echo "If clicks do not work, start ydotoold: sudo systemctl enable --now ydotool"
else
  echo "X11 session assumed; pyautogui should work with DISPLAY set."
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PIP_INDEX="https://pypi.tuna.tsinghua.edu.cn/simple"

echo "Installing Python dependencies (Tsinghua mirror)..."
if [ ! -d "${PROJECT_ROOT}/.venv" ]; then
  python3 -m venv "${PROJECT_ROOT}/.venv"
fi
"${PROJECT_ROOT}/.venv/bin/pip" install -i "${PIP_INDEX}" -r "${PROJECT_ROOT}/requirements.txt"

echo "Done. Activate: source ${PROJECT_ROOT}/.venv/bin/activate"
echo "Run: python -m src.monitor --pick-region"
