"""Composited application icon.

The original musical-note.png is a black glyph on transparency: it vanishes
against dark docks/taskbars (and the qtawesome glyphs have the same problem
in reverse on light themes). Compositing the note onto a rounded accent tile
keeps the icon visible on both light and dark desktop themes.

Run as a script to write a PNG for the desktop entry:
    venv/bin/python appicon.py fooqt6-icon.png
"""
import os
import sys

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication

NOTE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "musical-note.png")
TILE_TOP = QColor("#4a90d9")
TILE_BOTTOM = QColor("#2c6fb0")
GLYPH_COLOR = QColor("#ffffff")
BASE_SIZE = 512
ICON_SIZES = (16, 22, 24, 32, 48, 64, 128, 256, 512)

_APP = None


def _ensure_app():
    # keep a module-level reference so the QGuiApplication is not garbage
    # collected while pixmaps are still in use
    global _APP
    if QApplication.instance() is None:
        _APP = QApplication([])
    return QApplication.instance()


def _tinted(glyph: QPixmap, color: QColor) -> QPixmap:
    """Recolor a black-on-transparent glyph to a solid color, keeping alpha."""
    img = glyph.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(img.rect(), color)
    p.end()
    return QPixmap.fromImage(img)


def build_icon() -> QIcon:
    _ensure_app()
    icon = QIcon()

    note = QPixmap(NOTE_PATH)
    if note.isNull():
        return icon  # caller falls back to the raw file

    canvas = QPixmap(BASE_SIZE, BASE_SIZE)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # rounded gradient tile with a subtle border so the tile also reads as a
    # shape on light taskbars
    p.setPen(QColor(0, 0, 0, 40))
    p.setBrush(TILE_TOP)
    radius = BASE_SIZE * 0.22
    p.drawRoundedRect(QRect(4, 4, BASE_SIZE - 8, BASE_SIZE - 8), radius, radius)

    # white note centered on the tile
    margin = int(BASE_SIZE * 0.16)
    glyph = _tinted(note.scaled(
        BASE_SIZE - 2 * margin,
        BASE_SIZE - 2 * margin,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    ), GLYPH_COLOR)
    x = (BASE_SIZE - glyph.width()) // 2
    y = (BASE_SIZE - glyph.height()) // 2
    p.drawPixmap(x, y, glyph)
    p.end()

    for size in ICON_SIZES:
        icon.addPixmap(
            canvas.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    return icon


def save_png(path: str, size: int = 512) -> bool:
    icon = build_icon()
    if icon.isNull():
        return False
    return icon.pixmap(QSize(size, size)).save(path)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        out = sys.argv[1]
        if save_png(out):
            print("wrote %s" % out)
        else:
            print("failed to build icon from %s" % NOTE_PATH)
            sys.exit(1)
    else:
        print("usage: appicon.py <output.png>")