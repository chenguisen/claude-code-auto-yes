#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
if ! .venv/bin/python -c "import PySide6" 2>/dev/null; then
    echo "Installing dependencies..."
    .venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
fi

exec .venv/bin/python -m src.app
