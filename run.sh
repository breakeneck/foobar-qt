#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Use the venv's python and pip directly
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# Install/update dependencies
echo "Installing dependencies..."
$VENV_PIP install --upgrade pip
$VENV_PIP install -r "$SCRIPT_DIR/requirements.txt"

# Run the app
echo "Starting app..."
$VENV_PYTHON "$SCRIPT_DIR/main.py"
