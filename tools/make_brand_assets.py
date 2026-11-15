"""Erzeugt das EMUHUB-Logo und das App-Icon aus Vektorformen (kein Zusatzpaket außer PySide6).

Aufruf:  py tools\\make_brand_assets.py [Zielordner]      (Standard: emu_launcher\\assets)
Ergebnis: icon.ico (16–256 px), icon.png (1024), logo.png (800×200, transparent),
          source\\icon.svg und source\\logo.svg (zum Weiterbearbeiten z. B. in Inkscape)

Idee: Das „H“ in EMUHUB besteht aus drei Kacheln – zwei Spiele-Cover und ein Verbinder –
in den Emulator-Farben der App (Ryujinx blau, Eglantine lila, Citra orange). Flach, ohne Verläufe.
Farben, Kachelmaße und Schrift lassen sich oben in den Konstanten ändern.
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

# Hinweis: nicht mit QT_QPA_PLATFORM=offscreen starten – dort fehlen die Schrift-Umrisse (Buchstaben werden zu Kästchen).

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontInfo, QFontMetricsF, QGuiApplication, QImage, QPainter, QPainterPath,
)
from PySide6.QtSvg import QSvgGenerator

# ------------------------------------------------------------------ Gestaltung
TILE_COLORS = ("#3b82f6", "#a855f7", "#f97316")   # links, Verbinder, rechts
BACKGROUND = "#131a2e"                            # dunkle Fläche des App-Icons
INK = "#eef2ff"                                   # Buchstaben im Logo
FONT_CANDIDATES = ("Bahnschrift", "Segoe UI", "Arial")
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

# Maße des H in Einheiten (Höhe = 100)
TILE_W, BAR_W, GAP = 32.0, 40.0, 5.0
MARK_W = TILE_W * 2 + BAR_W + GAP * 2             # 114
# im Schriftzug schlankere Stege, damit das H neben den Buchstaben als H gelesen wird
LOGO_TILE_W, LOGO_BAR_W, LOGO_GAP = 21.0, 36.0, 4.0


def draw_mark(p: QPainter, x: float, y: float, h: float, *, bar_h: float = 24.0, gap: float = GAP,
              radius: float = 8.0, snap: bool = False, tile_w: float = TILE_W, bar_w: float = BAR_W) -> float:
    """Zeichnet das Kachel-H mit linker oberer Ecke (x, y) und Höhe h. Gibt die Breite zurück."""
    s = h / 100.0
    tw, bw, g = tile_w * s, bar_w * s, gap * s
    width = tw * 2 + bw + g * 2
    bh = bar_h * s
    rects = [
        QRectF(x, y, tw, h),
        QRectF(x + tw + g, y + (h - bh) / 2, bw, bh),
        QRectF(x + tw + g + bw + g, y, tw, h),
    ]
    if snap:  # bei kleinen Größen auf ganze Pixel legen, sonst werden Kanten unscharf
        rects = [QRectF(round(r.x()), round(r.y()), max(1, round(r.width())), max(1, round(r.height()))) for r in rects]
    r = radius * s
    p.setPen(Qt.PenStyle.NoPen)
    for rect, color in zip(rects, TILE_COLORS):
        p.setBrush(QColor(color))
        p.drawRoundedRect(rect, r, r)
    return width


# ------------------------------------------------------------------ App-Icon
def draw_icon(p: QPainter, size: int) -> None:
    small = size <= 32
    pad = 0.12 if size <= 24 else 0.16 if small else 0.2
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(BACKGROUND))
    corner = size * 0.225
    p.drawRoundedRect(QRectF(0, 0, size, size), corner, corner)
    h = size * (1 - 2 * pad)
    w = h * MARK_W / 100.0
    # kleine Größen: dickere Brücke, größere Lücken, eckigere Kacheln – bleibt lesbar
    draw_mark(p, (size - w) / 2, (size - h) / 2, h,
              bar_h=32.0 if small else 24.0, gap=7.0 if small else GAP,
              radius=6.0 if small else 8.0, snap=size <= 48)


# ------------------------------------------------------------------ Logo
def pick_font(px: int) -> QFont:
    for family in FONT_CANDIDATES:
        font = QFont(family)
        if QFontInfo(font).family().lower().startswith(family.lower()):
            break
    font.setPixelSize(px)
    font.setWeight(QFont.Weight.Bold)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px * 0.03)
    return font


def text_path(text: str, font: QFont) -> QPainterPath:
    path = QPainterPath()
    path.addText(0, 0, font, text)   # Grundlinie bei y = 0 -> Schrift wird zu Vektorform
    return path


def draw_logo(p: QPainter, width: int, height: int) -> None:
    """EMU + [Kachel-H] + UB, mittig; Buchstaben als Pfade (unabhängig von installierten Schriften)."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    font = pick_font(100)
    cap = QFontMetricsF(font).capHeight()
    emu, ub = text_path("EMU", font), text_path("UB", font)
    gap = cap * 0.2     # Luft zwischen Buchstaben und Kachel-H
    emu_w, ub_w = emu.boundingRect().right(), ub.boundingRect().right() - ub.boundingRect().left()
    mark_w = cap * (2 * LOGO_TILE_W + LOGO_BAR_W + 2 * LOGO_GAP) / 100.0
    total = emu_w + gap + mark_w + gap + ub_w
    scale = min(height * 0.66 / cap, width * 0.94 / total)
    p.save()
    p.translate((width - total * scale) / 2, (height + cap * scale) / 2)   # Grundlinie
    p.scale(scale, scale)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(INK))
    p.drawPath(emu)
    mark_x = emu_w + gap
    draw_mark(p, mark_x, -cap, cap, bar_h=17.0, gap=LOGO_GAP, radius=5.0, tile_w=LOGO_TILE_W, bar_w=LOGO_BAR_W)
    p.translate(mark_x + mark_w + gap - ub.boundingRect().left(), 0)
    p.drawPath(ub)
    p.restore()


# ------------------------------------------------------------------ Ausgabe
def render_image(w: int, h: int, draw) -> QImage:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    draw(p)
    p.end()
    return img


def write_svg(path: Path, w: int, h: int, draw) -> None:
    gen = QSvgGenerator()
    gen.setFileName(str(path))
    gen.setSize(QSize(w, h))
    gen.setViewBox(QRectF(0, 0, w, h))
    p = QPainter(gen)
    draw(p)
    p.end()


def png_bytes(img: QImage) -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def write_ico(path: Path, sizes) -> None:
    """ICO mit je einer PNG-Ebene pro Größe (Windows Vista und neuer)."""
    blobs = [(s, png_bytes(render_image(s, s, lambda p, s=s: draw_icon(p, s)))) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries, data = b"", b""
    for s, blob in blobs:
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset + len(data))
        data += blob
    path.write_bytes(header + entries + data)


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    here = Path(__file__).resolve().parent.parent
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "emu_launcher" / "assets"
    (out / "source").mkdir(parents=True, exist_ok=True)

    render_image(1024, 1024, lambda p: draw_icon(p, 1024)).save(str(out / "icon.png"))
    write_ico(out / "icon.ico", ICON_SIZES)
    render_image(800, 200, lambda p: draw_logo(p, 800, 200)).save(str(out / "logo.png"))
    write_svg(out / "source" / "icon.svg", 1024, 1024, lambda p: draw_icon(p, 1024))
    write_svg(out / "source" / "logo.svg", 800, 200, lambda p: draw_logo(p, 800, 200))
    print("geschrieben in", out)
    for f in sorted(out.rglob("*")):
        if f.is_file() and f.name != "README.md":
            print(f"  {f.relative_to(out)}  {f.stat().st_size} Byte")


if __name__ == "__main__":
    main()
