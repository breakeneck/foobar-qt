#!/bin/bash
# Installs (or removes) a desktop entry so FooQt6 shows up in the Linux
# main menu / application launcher.
#
#   ./install_menu_icon.sh           # create the menu entry
#   ./install_menu_icon.sh --remove  # remove it again

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$APPS_DIR/fooqt6.desktop"
DESKTOP_ID="fooqt6"

set -e

if [ "$1" = "--remove" ]; then
    if [ -f "$DESKTOP_FILE" ]; then
        rm "$DESKTOP_FILE"
        echo "Removed $DESKTOP_FILE"
    else
        echo "No desktop entry at $DESKTOP_FILE"
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$APPS_DIR" 2>/dev/null || true
    fi
    exit 0
fi

if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

mkdir -p "$APPS_DIR"

# Render a theme-proof app icon (white note on a colored tile) so the entry
# is visible in both light and dark menus/docks; fall back to the raw PNG.
ICON_PNG="$SCRIPT_DIR/fooqt6-icon.png"
if QT_QPA_PLATFORM=offscreen "$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/appicon.py" "$ICON_PNG" >/dev/null 2>&1; then
    ICON_PATH="$ICON_PNG"
else
    ICON_PATH="$SCRIPT_DIR/musical-note.png"
fi

# Path= keeps the cwd at the project dir, so config.json/db.sqlite3 always
# live next to the app no matter how it is launched.
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=FooQt6
GenericName=Music Player
Comment=PyQt6 music player with local and SFTP library support
Exec=bash "$SCRIPT_DIR/run.sh"
Path=$SCRIPT_DIR
Icon=$ICON_PATH
Terminal=false
Categories=AudioVideo;Audio;Player;Qt;
EOF

chmod 644 "$DESKTOP_FILE"

if command -v desktop-file-validate >/dev/null 2>&1; then
    if desktop-file-validate "$DESKTOP_FILE"; then
        echo "Desktop entry validated."
    else
        echo "Warning: desktop-file-validate reported issues (see above)."
    fi
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS_DIR" 2>/dev/null || true
fi

echo "Installed menu entry: $DESKTOP_FILE"
echo "Look for 'FooQt6' in your application menu."