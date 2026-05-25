#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

VENV_PYTHON="$VENV_DIR/bin/python"

echo "Starting app..."
$VENV_PYTHON "$SCRIPT_DIR/main.py"
