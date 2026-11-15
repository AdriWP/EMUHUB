"""Wiederverwendbare Widgets: FlowLayout, Spielekachel, Badge, Detail-Seitenleiste."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime

from PySide6.QtCore import QEasingCurve, QPoint, QRect, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPixmap,
)
from PySide6.QtWidgets import (
    QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLayout, QLineEdit, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from data_manager import CARD_COVER_H, EMULATORS, cover_aspect
from i18n import tr


# --------------------------------------------------------------------- Helfer
def screen_dpr() -> float:
    screen = QGuiApplication.primaryScreen()
    return screen.devicePixelRatio() if screen else 1.0


def _draw_cropped(p: QPainter, src: QPixmap, rect: QRect) -> None:
    """Bild füllt rect komplett aus (mittig zugeschnitten)."""
    scaled = src.scaled(rect.width(), rect.height(),
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation)
    sx = (scaled.width() - rect.width()) // 2
    sy = (scaled.height() - rect.height()) // 2
    p.drawPixmap(rect.x(), rect.y(), scaled, sx, sy, rect.width(), rect.height())


def _draw_placeholder(p: QPainter, rect: QRect, emulator: str, title: str) -> None:
    color = QColor(EMULATORS.get(emulator, "#5b8cff"))
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, color.lighter(115))
    grad.setColorAt(0.55, color.darker(165))
    grad.setColorAt(1.0, QColor("#0d0f1a"))
    p.fillRect(rect, grad)
    words = [wd for wd in title.split() if wd[:1].isalnum()]
    initials = "".join(wd[0] for wd in words[:2]).upper() or "?"
    font = QFont()
    font.setPixelSize(max(12, int(min(rect.width(), rect.height()) * 0.28)))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor(255, 255, 255, 220))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, initials)


def make_cover_pixmap(path: str, w: int, h: int, emulator: str, title: str,
                      radius: int = 10) -> QPixmap:
    """Zeichnet ein Cover mittig zugeschnitten mit abgerundeten Ecken in Größe w×h
    (Hochformat oder Quadrat). Ohne Bild: Platzhalter mit Initialen in Emulator-Farbe."""
    dpr = screen_dpr()
    pw, ph = int(w * dpr), int(h * dpr)
    result = QPixmap(pw, ph)
    result.fill(Qt.GlobalColor.transparent)

    p = QPainter(result)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    full = QRect(0, 0, pw, ph)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(full), radius * dpr, radius * dpr)
    p.setClipPath(clip)

    src = QPixmap(path) if path and os.path.isfile(path) else QPixmap()
    if not src.isNull():
        _draw_cropped(p, src, full)
    else:
        _draw_placeholder(p, full, emulator, title)
    p.end()
    result.setDevicePixelRatio(dpr)
    return result


def open_in_file_manager(path: str, parent: QWidget | None = None) -> None:
    if not path or not os.path.isdir(path):
        QMessageBox.warning(parent, tr("Ordner nicht gefunden"),
                            tr("Der Ordner existiert nicht:\n{path}", path=path or tr("(kein Pfad)")))
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError as exc:
        QMessageBox.critical(parent, tr("Fehler"), tr("Ordner konnte nicht geöffnet werden:\n{exc}", exc=exc))


def ask_yes_no(parent: QWidget | None, title: str, text: str, default_yes: bool = True) -> bool:
    """Ja/Nein-Frage mit übersetzten Knöpfen (Qt-Standardknöpfe wären immer englisch)."""
    box = QMessageBox(QMessageBox.Icon.Question, title, text,
                      QMessageBox.StandardButton.NoButton, parent)
    yes = box.addButton(tr("Ja"), QMessageBox.ButtonRole.YesRole)
    no = box.addButton(tr("Nein"), QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(yes if default_yes else no)
    box.setEscapeButton(no)
    box.exec()
    return box.clickedButton() is yes


def format_timestamp(iso: str) -> str:
    if not iso:
        return tr("Noch nie")
    try:
        return datetime.fromisoformat(iso).strftime(tr("%d.%m.%Y, %H:%M Uhr"))
    except ValueError:
        return iso


# ---------------------------------------------------------- Hintergrundbild
class BackgroundWidget(QWidget):
    """Zentrales Widget, das ein optionales Hintergrundbild (fensterfüllend,
    mittig zugeschnitten) plus Abdunklung zeichnet. Ohne Bild bleibt es
    transparent und der Theme-Farbverlauf ist sichtbar."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._src = QPixmap()
        self._cache = QPixmap()
        self._dim = 0.55

    def set_background(self, path: str, dim_percent: int) -> None:
        self._src = QPixmap(path) if path and os.path.isfile(path) else QPixmap()
        self._dim = max(0, min(90, int(dim_percent))) / 100
        self._cache = QPixmap()
        self.update()

    def resizeEvent(self, event):
        self._cache = QPixmap()
        super().resizeEvent(event)

    def paintEvent(self, event):
        if self._src.isNull():
            return
        dpr = self.devicePixelRatioF()
        pw, ph = int(self.width() * dpr), int(self.height() * dpr)
        if self._cache.isNull() or self._cache.width() != pw or self._cache.height() != ph:
            scaled = self._src.scaled(pw, ph, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                      Qt.TransformationMode.SmoothTransformation)
            self._cache = scaled.copy((scaled.width() - pw) // 2, (scaled.height() - ph) // 2,
                                      pw, ph)
            self._cache.setDevicePixelRatio(dpr)
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache)
        p.fillRect(self.rect(), QColor(0, 0, 0, int(255 * self._dim)))
        p.end()


# ----------------------------------------------------------------- FlowLayout
class FlowLayout(QLayout):
    """Layout, das Kacheln zeilenweise anordnet und bei Platzmangel umbricht.
    Versteckte Widgets werden übersprungen (für Filter/Suche)."""

    def __init__(self, parent: QWidget | None = None, margin: int = 0,
                 h_spacing: int = 18, v_spacing: int = 18):
        super().__init__(parent)
        self._items = []
        self._h = h_spacing
        self._v = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        visible = [it for it in self._items
                   if it.widget() is None or not it.widget().isHidden()]
        if not visible:
            return m.top() + m.bottom()

        # Kacheln sind gleich hoch, aber unterschiedlich breit (Hochformat/Quadrat).
        # 1) Zeilen füllen, solange Platz ist
        def hint(it) -> QSize:
            # Kacheln melden ihre Grundgröße – ein Hover-Zoom verschiebt nichts im Raster
            return getattr(it.widget(), "base_size", None) or it.sizeHint()

        rows: list[list] = [[]]
        row_w = 0
        for it in visible:
            w = hint(it).width()
            needed = w if not rows[-1] else row_w + self._h + w
            if rows[-1] and needed > eff.width():
                rows.append([])
                needed = w
            rows[-1].append(it)
            row_w = needed
        # 2) Gesamtblock mittig, Zeilen darin linksbündig
        widths = [sum(hint(it).width() for it in r) + self._h * (len(r) - 1) for r in rows]
        x0 = eff.x() + max(0, (eff.width() - max(widths)) // 2)

        y = eff.y()
        for row in rows:
            row_h = max(hint(it).height() for it in row)
            x = x0
            for it in row:
                size = hint(it)
                if not test_only:
                    rect = QRect(QPoint(x, y), size)
                    w = it.widget()
                    if hasattr(w, "set_layout_rect"):
                        w.set_layout_rect(rect)  # Kachel kümmert sich selbst um ihren Zoom
                    else:
                        it.setGeometry(rect)
                x += size.width() + self._h
            y += row_h + self._v
        return y - self._v - rect.y() + m.bottom()


# ------------------------------------------------------------------ ZoomCover
class ZoomCover(QWidget):
    """Zeigt ein (hochaufgelöstes) Cover-Pixmap immer passend zur aktuellen
    Widget-Größe – dadurch kann die Kachel beim Hovern weich vergrößert werden."""

    def __init__(self, pixmap: QPixmap, parent: QWidget | None = None):
        super().__init__(parent)
        self._pixmap = pixmap

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(self.rect(), self._pixmap)
        p.end()


# ---------------------------------------------------------------------- Badge
class Badge(QLabel):
    def __init__(self, emulator: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.set_emulator(emulator)

    def set_emulator(self, emulator: str) -> None:
        color = EMULATORS.get(emulator, "#6b7280")
        self.setText(emulator or "?")
        self.setStyleSheet(
            f"background-color: {color}; color: #ffffff; border-radius: 6px;"
            "padding: 2px 9px; font-size: 8pt; font-weight: 700;"
        )
        self.adjustSize()


# ------------------------------------------------------------------- GameCard
class GameCard(QFrame):
    clicked = Signal(str)
    double_clicked = Signal(str)
    context_requested = Signal(str, QPoint)
    favorite_toggled = Signal(str)

    EXTRA_H = 80       # Platz für Titel + Badge unter dem Cover
    HOVER_ZOOM = 0.07  # Kachel wächst beim Drüberfahren um 7 %

    def __init__(self, game: dict, cover_abs_path: str, scale: float = 1.0,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.game_id = game["id"]
        self.search_text = game["name"].lower()
        self.emulator = game["emulator"]

        self.setObjectName("GameCard")
        self.setProperty("selected", False)
        self.setProperty("emu", game["emulator"])  # für farbigen Hover/Auswahl im QSS
        # Alle Kacheln haben dieselbe Höhe (skaliert mit der Kachelgröße). Die Breite
        # folgt dem Seitenverhältnis des Bildes – Switch-Cover hoch, 3DS-Icons quadratisch,
        # und das Bild wird vollständig gezeigt statt abgeschnitten.
        cover_h = int(CARD_COVER_H * scale)
        cover_w = int(round(cover_h * cover_aspect(game, cover_abs_path)))
        self.base_size = QSize(cover_w + 18, cover_h + self.EXTRA_H)  # Größe im Raster
        self._cover_base = QSize(cover_w, cover_h)
        self._layout_rect = QRect(QPoint(0, 0), self.base_size)
        self._zoom = 0.0          # 0 = normal, 1 = voll vergrößert (Hover)
        self._hover = False       # Maus über der Kachel (eigenes Flag, nicht underMouse())
        self._selected = False
        self.setFixedSize(self.base_size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("{name}\nDoppelklick zum Starten", name=game["name"]))

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._apply_zoom)
        self._anim.finished.connect(self._after_zoom_out)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 9, 9, 10)
        lay.setSpacing(8)

        # Cover in Zoom-Auflösung rendern, damit es beim Vergrößern scharf bleibt
        f = 1 + self.HOVER_ZOOM
        self.cover = ZoomCover(make_cover_pixmap(
            cover_abs_path, int(cover_w * f), int(cover_h * f), game["emulator"], game["name"],
            radius=max(6, int(10 * scale * f))))
        self.cover.setFixedSize(cover_w, cover_h)
        cover = self.cover
        lay.addWidget(cover)

        # Favoriten-Stern oben rechts auf dem Cover (★ = Favorit, ☆ nur beim Hovern)
        self.favorite = bool(game.get("favorite", False))
        self.star = QLabel(cover)
        self.star.setObjectName("FavStar")
        self.star.setFixedSize(30, 30)
        self.star.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.star.move(cover_w - 36, 6)
        self._update_star(hover=False)

        title = QLabel()
        title.setObjectName("CardTitle")
        bold = QFont(title.font())
        bold.setBold(True)
        title.setText(QFontMetrics(bold).elidedText(
            game["name"], Qt.TextElideMode.ElideRight, cover_w - 4))
        lay.addWidget(title)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(Badge(game["emulator"]))
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)

        # Alle Mausereignisse landen bei der Karte selbst
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self._update_shadow()
        self.update()

    def _update_shadow(self) -> None:
        """Ausgewählt: Leuchten in Emulator-Farbe. Hover: dunkler Schatten (wirkt angehoben)."""
        if self._selected:
            effect = QGraphicsDropShadowEffect(self)
            color = QColor(EMULATORS.get(self.emulator, "#5b8cff"))
            color.setAlpha(170)
            effect.setColor(color)
            effect.setBlurRadius(32)
            effect.setOffset(0, 0)
            self.setGraphicsEffect(effect)
        elif self._zoom > 0 or self._hover:
            effect = QGraphicsDropShadowEffect(self)
            effect.setColor(QColor(0, 0, 0, 170))
            effect.setBlurRadius(30)
            effect.setOffset(0, 10)
            self.setGraphicsEffect(effect)
        else:
            self.setGraphicsEffect(None)

    # --------------------------------------------------------------- Hover-Zoom
    def set_layout_rect(self, rect: QRect) -> None:
        """Wird vom FlowLayout aufgerufen: Grundposition im Raster."""
        self._layout_rect = QRect(rect)
        self._apply_zoom(self._zoom)

    def _apply_zoom(self, value) -> None:
        self._zoom = float(value)
        f = 1 + self.HOVER_ZOOM * self._zoom
        cw = int(round(self._cover_base.width() * f))
        ch = int(round(self._cover_base.height() * f))
        size = QSize(cw + 18, self.base_size.height() + (ch - self._cover_base.height()))
        self.cover.setFixedSize(cw, ch)
        self.star.move(cw - 36, 6)
        rect = QRect(QPoint(0, 0), size)
        rect.moveCenter(self._layout_rect.center())
        self.setFixedSize(size)
        self.setGeometry(rect)

    def _animate_zoom(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._zoom)
        self._anim.setEndValue(target)
        self._anim.start()

    # ---------------------------------------------------------- Favoriten-Stern
    def _update_star(self, hover: bool) -> None:
        self.star.setProperty("active", self.favorite)
        self.star.setText("★" if self.favorite else "☆")
        self.star.setToolTip(tr("Aus Favoriten entfernen") if self.favorite
                             else tr("Zu Favoriten hinzufügen"))
        self.star.setVisible(self.favorite or hover)
        self.star.style().unpolish(self.star)
        self.star.style().polish(self.star)

    def _star_hit(self, pos: QPoint) -> bool:
        if not self.star.isVisible():
            return False
        rect = self.star.geometry().translated(self.star.parentWidget().pos())
        return rect.adjusted(-4, -4, 4, 4).contains(pos)

    def enterEvent(self, event):
        self._hover = True
        self._update_star(hover=True)
        self.raise_()  # vergrößerte Kachel liegt über den Nachbarn
        self._animate_zoom(1.0)
        self._update_shadow()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self._update_star(hover=False)
        if not self.property("pad"):  # per Controller fokussierte Kachel bleibt vergrößert
            self._animate_zoom(0.0)
        super().leaveEvent(event)

    def set_pad_focus(self, on: bool) -> None:
        """Controller-Fokus: weißer Rahmen (QSS) und dauerhaft vergrößert."""
        if bool(self.property("pad")) == bool(on):
            return  # nichts geändert – z. B. erneuter Klick auf die ausgewählte Kachel
        self.setProperty("pad", bool(on))
        self.style().unpolish(self)
        self.style().polish(self)
        if on:
            self.raise_()
            self._animate_zoom(1.0)
        elif not self._hover:  # Maus noch auf der Kachel: Hover-Zoom bleibt
            self._animate_zoom(0.0)

    def _after_zoom_out(self) -> None:
        if self._zoom == 0:
            self._update_shadow()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._star_hit(event.position().toPoint()):
                self.favorite_toggled.emit(self.game_id)
                return
            self.clicked.emit(self.game_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._star_hit(event.position().toPoint()):
                return  # schneller Doppelklick auf den Stern startet nicht das Spiel
            self.double_clicked.emit(self.game_id)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.clicked.emit(self.game_id)
        self.context_requested.emit(self.game_id, event.globalPos())


# --------------------------------------------------------------- DetailsPanel
class DetailsPanel(QFrame):
    launch_requested = Signal(str)
    edit_requested = Signal(str)
    delete_requested = Signal(str)
    favorite_requested = Signal(str)
    screenshots_requested = Signal(str)

    COVER_H = 280       # einheitliche Cover-Höhe in der Seitenleiste
    COVER_MAX_W = 326   # maximal verfügbare Breite

    def __init__(self, data_manager, parent: QWidget | None = None):
        super().__init__(parent)
        self.data = data_manager
        self.game_id: str | None = None
        self.setObjectName("DetailsPanel")
        self.setFixedWidth(370)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        # Seite 0: nichts ausgewählt
        placeholder = QLabel(tr("Wähle ein Spiel aus,\num Details, Mods und\nStartparameter zu sehen."))
        placeholder.setObjectName("Placeholder")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stack.addWidget(placeholder)

        # Seite 1: Details
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("DetailsInner")
        scroll.setWidget(inner)
        self.stack.addWidget(scroll)

        lay = QVBoxLayout(inner)
        lay.setContentsMargins(22, 22, 22, 22)
        lay.setSpacing(10)

        self.cover = QLabel()
        self.cover.setFixedSize(210, self.COVER_H)
        lay.addWidget(self.cover, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(6)

        self.title = QLabel()
        self.title.setObjectName("DetailsTitle")
        self.title.setWordWrap(True)
        lay.addWidget(self.title)

        # Zeile: Emulator-Badge ... Favoriten-Stern
        badge_row = QHBoxLayout()
        self.badge = Badge()
        badge_row.addWidget(self.badge)
        badge_row.addStretch(1)
        lay.addLayout(badge_row)
        # "Zuletzt gespielt" in eigener, umbrechender Zeile – lange Datumsangaben
        # dürfen die Seitenleiste nicht verbreitern.
        self.played = QLabel()
        self.played.setObjectName("MetaLabel")
        self.played.setWordWrap(True)
        self.played.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(self.played)
        lay.addSpacing(4)

        btn_row = QHBoxLayout()
        self.btn_launch = QPushButton(tr("▶  Starten"))
        self.btn_launch.setObjectName("PrimaryButton")
        self.btn_edit = QPushButton(tr("Bearbeiten"))
        self.btn_delete = QPushButton(tr("Löschen"))
        self.btn_delete.setObjectName("DangerButton")
        self.btn_fav = QPushButton("☆")
        self.btn_fav.setObjectName("FavButton")
        self.btn_fav.setCheckable(True)
        self.btn_fav.setFixedWidth(42)
        for b in (self.btn_launch, self.btn_edit, self.btn_delete, self.btn_fav):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        badge_row.addWidget(self.btn_fav)  # Stern rechts neben dem Emulator-Badge
        btn_row.addWidget(self.btn_launch, 2)
        btn_row.addWidget(self.btn_edit, 1)
        btn_row.addWidget(self.btn_delete, 1)
        lay.addLayout(btn_row)
        self.btn_shots = QPushButton(tr("📷  Screenshots ansehen"))
        self.btn_shots.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.btn_shots)
        lay.addSpacing(8)

        self.emu_field = self._add_field(lay, tr("EMULATOR-PFAD"))
        self.rom_field = self._add_field(lay, tr("ROM-DATEI"))
        self.args_field = self._add_field(lay, tr("STARTPARAMETER"))

        lay.addWidget(self._section(tr("NOTIZEN & AKTIVE MODS")))
        self.notes = QPlainTextEdit()
        self.notes.setObjectName("NotesView")
        self.notes.setReadOnly(True)
        self.notes.setMinimumHeight(140)
        lay.addWidget(self.notes)

        self.mod_field = self._add_field(lay, tr("MOD-ORDNER"))
        self.btn_mods = QPushButton(tr("📂  Mod-Ordner im Explorer öffnen"))
        self.btn_mods.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.btn_mods)
        lay.addStretch(1)

        self.btn_launch.clicked.connect(lambda: self.game_id and self.launch_requested.emit(self.game_id))
        self.btn_edit.clicked.connect(lambda: self.game_id and self.edit_requested.emit(self.game_id))
        self.btn_delete.clicked.connect(lambda: self.game_id and self.delete_requested.emit(self.game_id))
        self.btn_fav.clicked.connect(lambda: self.game_id and self.favorite_requested.emit(self.game_id))
        self.btn_mods.clicked.connect(lambda: open_in_file_manager(self.mod_field.text(), self))
        self.btn_shots.clicked.connect(lambda: self.game_id and self.screenshots_requested.emit(self.game_id))

    @staticmethod
    def _section(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("SectionLabel")
        return lbl

    def _add_field(self, lay: QVBoxLayout, label: str) -> QLineEdit:
        lay.addWidget(self._section(label))
        field = QLineEdit()
        field.setReadOnly(True)
        lay.addWidget(field)
        return field

    @staticmethod
    def _set_field(field: QLineEdit, value: str, empty: str = "—") -> None:
        field.setText(value or "")
        field.setPlaceholderText(empty)
        field.setToolTip(value or "")
        field.setCursorPosition(0)

    def clear(self) -> None:
        self.game_id = None
        self.stack.setCurrentIndex(0)

    def show_game(self, game: dict | None) -> None:
        if game is None:
            self.clear()
            return
        self.game_id = game["id"]
        aspect = cover_aspect(game, self.data.abs_path(game["cover"]))
        h = self.COVER_H
        w = int(round(h * aspect))
        if w > self.COVER_MAX_W:  # sehr breite Bilder: Höhe verkleinern statt abschneiden
            w = self.COVER_MAX_W
            h = int(round(w / aspect))
        self.cover.setFixedSize(w, h)
        self.cover.setPixmap(make_cover_pixmap(
            self.data.abs_path(game["cover"]), w, h,
            game["emulator"], game["name"], radius=14))
        self.title.setText(game["name"])
        self.badge.set_emulator(game["emulator"])
        fav = bool(game.get("favorite", False))
        self.btn_fav.setChecked(fav)
        self.btn_fav.setText("★" if fav else "☆")
        self.btn_fav.setToolTip(tr("Aus Favoriten entfernen") if fav else tr("Zu Favoriten hinzufügen"))
        count = game.get("play_count", 0)
        self.played.setText(tr("Zuletzt: {when}", when=format_timestamp(game.get("last_played", "")))
                            + (tr("  ·  {count}× gestartet", count=count) if count else ""))

        emu_path = self.data.resolve_emulator_path(game)
        self._set_field(self.emu_field, emu_path, tr("Kein Emulator-Pfad hinterlegt"))
        self._set_field(self.rom_field, game["rom_path"], tr("Keine ROM hinterlegt"))
        args = self.data.resolve_args(game)
        shown = args if (game.get("args") or "").strip() or not args else tr("{args}  (Emulator-Standard)", args=args)
        self._set_field(self.args_field, shown, tr("Keine Startparameter"))
        self.notes.setPlainText(game["notes"])
        self.notes.setPlaceholderText(tr("Keine Notizen oder Mods hinterlegt."))
        self._set_field(self.mod_field, game["mod_path"], tr("Kein Mod-Ordner hinterlegt"))
        self.btn_mods.setEnabled(bool(game["mod_path"]))
        self.stack.setCurrentIndex(1)
