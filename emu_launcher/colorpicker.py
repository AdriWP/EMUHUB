"""Farbwähler: Fläche für Sättigung/Helligkeit + senkrechte Farbtonleiste + Hex-Feld.

Eigenes Widget statt QColorDialog, damit Aussehen und Texte (Deutsch/English) zu EMUHUB passen.
Signal `colorChanged(QColor)` kommt bei jeder Änderung durch den Nutzer *und* bei setColor().
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from i18n import tr


def valid_hex(text: str) -> bool:
    text = (text or "").strip()
    return len(text) in (4, 7) and text.startswith("#") and QColor.isValidColorName(text)


class _Surface(QWidget):
    """Gemeinsame Basis: Maus ziehen -> Position als 0..1 melden."""
    moved = Signal(float, float)

    def __init__(self):
        super().__init__()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(False)

    def _emit(self, pos) -> None:
        w, h = max(1, self.width() - 1), max(1, self.height() - 1)
        self.moved.emit(min(1.0, max(0.0, pos.x() / w)), min(1.0, max(0.0, pos.y() / h)))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._emit(e.position())

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._emit(e.position())


class _SVSquare(_Surface):
    def __init__(self):
        super().__init__()
        self.hue, self.sat, self.val = 0.0, 1.0, 1.0
        self.setMinimumSize(200, 200)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(r, 6, 6)
        p.setClipPath(clip)
        horiz = QLinearGradient(r.left(), 0, r.right(), 0)       # weiß -> reine Farbe
        horiz.setColorAt(0, QColor("#ffffff"))
        horiz.setColorAt(1, QColor.fromHsvF(self.hue, 1, 1))
        p.fillRect(r, horiz)
        vert = QLinearGradient(0, r.top(), 0, r.bottom())        # durchsichtig -> schwarz
        vert.setColorAt(0, QColor(0, 0, 0, 0))
        vert.setColorAt(1, QColor(0, 0, 0, 255))
        p.fillRect(r, vert)
        p.setClipping(False)
        x, y = r.left() + self.sat * r.width(), r.top() + (1 - self.val) * r.height()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 160), 4))
        p.drawEllipse(QPointF(x, y), 8, 8)
        p.setPen(QPen(QColor("#ffffff"), 2.5))
        p.drawEllipse(QPointF(x, y), 8, 8)


class _HueBar(_Surface):
    def __init__(self):
        super().__init__()
        self.hue = 0.0
        self.setFixedWidth(26)
        self.setMinimumHeight(200)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        grad = QLinearGradient(0, r.top(), 0, r.bottom())
        for i in range(7):
            grad.setColorAt(i / 6, QColor.fromHsvF((i % 6) / 6 if i < 6 else 0.9999, 1, 1))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, 6, 6)
        y = r.top() + self.hue * r.height()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 160), 4))
        p.drawRoundedRect(QRectF(r.left() - 1, y - 3, r.width() + 2, 6), 3, 3)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawRoundedRect(QRectF(r.left() - 1, y - 3, r.width() + 2, 6), 3, 3)


class ColorPicker(QWidget):
    colorChanged = Signal(QColor)

    def __init__(self, color: str | QColor = "#4f7bff", parent: QWidget | None = None, title: bool = True):
        super().__init__(parent)
        self._h, self._s, self._v = 0.0, 1.0, 1.0
        self._exact: QColor | None = None   # exakt gesetzte Farbe (HSV-Umrechnung kann um 1 abweichen)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)
        if title:
            head = QLabel(tr("Farbwähler"))
            head.setObjectName("SectionLabel")
            head.setStyleSheet("font-weight: 800;")
            root.addWidget(head)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.square = _SVSquare()
        self.bar = _HueBar()
        row.addWidget(self.square, 1)
        row.addWidget(self.bar)
        root.addLayout(row, 1)
        hex_row = QHBoxLayout()
        self.hex_edit = QLineEdit()
        self.hex_edit.setMaxLength(7)
        self.hex_edit.setPlaceholderText("#rrggbb")
        self.hex_edit.setMaximumWidth(110)
        self.swatch = QLabel()
        self.swatch.setFixedSize(46, 26)
        hex_row.addWidget(self.hex_edit)
        hex_row.addWidget(self.swatch)
        hex_row.addStretch(1)
        root.addLayout(hex_row)

        self.square.moved.connect(self._on_square)
        self.bar.moved.connect(self._on_bar)
        self.hex_edit.textEdited.connect(self._on_hex)
        self.setColor(color, emit=False)

    # ------------------------------------------------------------------ API
    def color(self) -> QColor:
        return QColor(self._exact) if self._exact is not None else QColor.fromHsvF(self._h, self._s, self._v)

    def hex(self) -> str:
        return self.color().name()

    def setColor(self, color: str | QColor, emit: bool = True) -> None:
        c = QColor(color)
        if not c.isValid():
            return
        h = c.hsvHueF()
        if h >= 0:                      # bei Grau bleibt der bisherige Farbton erhalten
            self._h = h
        self._s, self._v = c.hsvSaturationF(), c.valueF()
        self._exact = QColor(c.name())
        self._sync(emit, update_hex=True)

    # ------------------------------------------------------------- intern
    def _sync(self, emit: bool, update_hex: bool) -> None:
        self.square.hue, self.square.sat, self.square.val = self._h, self._s, self._v
        self.bar.hue = self._h
        self.square.update()
        self.bar.update()
        c = self.color()
        self.swatch.setStyleSheet(f"background-color: {c.name()}; border-radius: 8px; border: 1px solid rgba(255,255,255,60);")
        if update_hex and self.hex_edit.text().lower() != c.name():
            self.hex_edit.setText(c.name())
        if emit:
            self.colorChanged.emit(c)

    def _on_square(self, x: float, y: float) -> None:
        self._s, self._v = x, 1 - y
        self._exact = None
        self._sync(True, True)

    def _on_bar(self, _x: float, y: float) -> None:
        self._h = min(y, 0.9999)
        self._exact = None
        self._sync(True, True)

    def _on_hex(self, text: str) -> None:
        text = text.strip()
        if not text.startswith("#") and text:
            text = "#" + text
            self.hex_edit.setText(text)
        if valid_hex(text) and len(text) == 7:   # erst bei vollständigem Wert (während des Tippens nicht eingreifen)
            self.setColor(text)


class ColorDialog(QDialog):
    """Kleiner Dialog um den Farbwähler (Ersatz für QColorDialog, mit deutschen/englischen Knöpfen)."""

    def __init__(self, color: str, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        self.picker = ColorPicker(color)
        root.addWidget(self.picker, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText(tr("Übernehmen"))
        ok.setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def chosen(self) -> str:
        return self.picker.hex()
