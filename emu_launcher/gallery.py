"""Screenshot-Galerie (Raster mit 16:9-Vorschauen) und große Einzelansicht."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QFont, QFontMetrics, QIcon, QImage, QImageReader, QPainter, QPainterPath, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from i18n import tr
from screenshots import Shot, find_screenshots, resolve_dir
from widgets import open_in_file_manager, screen_dpr

THUMB_W, THUMB_H = 224, 126     # 16:9
TILE_PAD = 8
GAP = 14
MAX_SHOWN = 300                 # nur die neuesten – hält die Galerie flott
ARROWS = (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down)


def fmt_time(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime(tr("%d.%m.%Y, %H:%M"))


# --------------------------------------------------------------- Vorschau-Thread
class ThumbWorker(QThread):
    """Lädt Vorschaubilder im Hintergrund (nur QImage – QPixmap gibt es nur im GUI-Thread)."""
    thumb = Signal(int, QImage, int)   # Index, Bild, Generation
    _active: set = set()               # starke Referenz bis der Thread beendet ist

    def __init__(self, paths: list[Path], size: QSize, generation: int):
        super().__init__()  # ohne Parent: überlebt das Schließen des Dialogs
        self._paths = [str(p) for p in paths]
        self._size = size
        self._gen = generation
        ThumbWorker._active.add(self)
        self.finished.connect(self._release)

    @classmethod
    def wait_all(cls, timeout_ms: int = 3000) -> None:
        for w in list(cls._active):
            w.requestInterruption()
            w.wait(timeout_ms)

    def _release(self) -> None:
        # nur die Referenz lösen; kein deleteLater(), denn die Galerie hält den Thread noch
        ThumbWorker._active.discard(self)

    def run(self) -> None:
        for i, path in enumerate(self._paths):
            if self.isInterruptionRequested():
                return
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            size = reader.size()
            if not size.isValid():
                continue
            reader.setScaledSize(size.scaled(self._size, Qt.AspectRatioMode.KeepAspectRatio))
            img = reader.read()
            if not img.isNull():
                self.thumb.emit(i, img, self._gen)


def thumb_pixmap(img: QImage) -> QPixmap:
    """16:9-Kachel mit dunklem Hintergrund; das Bild wird eingepasst, nie beschnitten."""
    dpr = screen_dpr()
    pm = QPixmap(int(THUMB_W * dpr), int(THUMB_H * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, THUMB_W, THUMB_H), 8, 8)
    p.setClipPath(clip)
    p.fillRect(QRectF(0, 0, THUMB_W, THUMB_H), Qt.GlobalColor.black)
    w, h = img.width() / dpr, img.height() / dpr
    p.drawImage(QRectF((THUMB_W - w) / 2, (THUMB_H - h) / 2, w, h), img)
    p.end()
    return pm


class ThumbButton(QToolButton):
    """Klickbare Vorschau. Pfeiltasten gibt sie an die Galerie weiter, statt selbst den Fokus zu verschieben."""
    navigate = Signal(int)

    def __init__(self, index: int, shot: Shot, parent: QWidget | None = None):
        super().__init__(parent)
        self.index = index
        self.setObjectName("ShotThumb")
        self.setFixedSize(THUMB_W + 2 * TILE_PAD + 4, THUMB_H + 2 * TILE_PAD + 4)
        self.setIconSize(QSize(THUMB_W, THUMB_H))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(f"{shot.path.name}\n{fmt_time(shot.mtime)}")

    def set_image(self, img: QImage) -> None:
        self.setIcon(QIcon(thumb_pixmap(img)))

    def keyPressEvent(self, event):
        if event.key() in ARROWS:
            self.navigate.emit(event.key())
            event.accept()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            event.accept()
        else:
            super().keyPressEvent(event)


# ---------------------------------------------------------------- Einzelansicht
class ScreenshotViewer(QDialog):
    def __init__(self, shots: list[Shot], index: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.shots = shots
        self.index = max(0, min(index, len(shots) - 1))
        self._pixmap = QPixmap()
        self.setObjectName("ViewerDialog")
        self.setWindowTitle("Screenshot")
        self.setModal(True)
        self.resize(1280, 760)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)
        mid = QHBoxLayout()
        mid.setSpacing(12)
        self.btn_prev = QPushButton("◀")
        self.btn_next = QPushButton("▶")
        self.btn_close = QPushButton(tr("✕  Schließen"))
        for b in (self.btn_prev, self.btn_next):
            b.setObjectName("ViewerNav")
        for b in (self.btn_prev, self.btn_next, self.btn_close):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # sonst schlucken sie die Pfeiltasten
            b.setAutoDefault(False)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(1, 1)
        self.image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        mid.addWidget(self.btn_prev, 0, Qt.AlignmentFlag.AlignVCenter)
        mid.addWidget(self.image, 1)
        mid.addWidget(self.btn_next, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(mid, 1)

        foot = QHBoxLayout()
        self.info = QLabel()
        self.info.setObjectName("ViewerInfo")
        foot.addWidget(self.info, 1)
        hint = QLabel(tr("◀ ▶ blättern   ·   Esc schließen"))
        hint.setObjectName("HintLabel")
        foot.addWidget(hint)
        foot.addWidget(self.btn_close)
        root.addLayout(foot)

        self.btn_prev.clicked.connect(lambda: self.go(-1))
        self.btn_next.clicked.connect(lambda: self.go(1))
        self.btn_close.clicked.connect(self.reject)
        self._load()

    def exec_maximized(self) -> int:
        self.setWindowState(Qt.WindowState.WindowMaximized)
        return self.exec()

    # ----------------------------------------------------------- Anzeige
    def _load(self) -> None:
        shot = self.shots[self.index]
        self._pixmap = QPixmap(str(shot.path))
        n = len(self.shots)
        size = f"  ·  {self._pixmap.width()}×{self._pixmap.height()}" if not self._pixmap.isNull() else ""
        self.info.setText(f"{self.index + 1} / {n}   ·   {shot.path.name}   ·   {fmt_time(shot.mtime)}{size}")
        self.btn_prev.setEnabled(self.index > 0)
        self.btn_next.setEnabled(self.index < n - 1)
        self._render()

    def _render(self) -> None:
        if self._pixmap.isNull():
            self.image.setPixmap(QPixmap())
            self.image.setText(tr("Bild konnte nicht geladen werden."))
            return
        dpr = self.devicePixelRatioF()
        target = self.image.size() * dpr
        scaled = self._pixmap.scaled(target, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        self.image.setText("")
        self.image.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def go(self, delta: int) -> None:
        new = max(0, min(len(self.shots) - 1, self.index + delta))
        if new != self.index:
            self.index = new
            self._load()

    # --------------------------------------------------------- Bedienung
    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
            self.go(-1)
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_PageDown, Qt.Key.Key_Space):
            self.go(1)
        elif key == Qt.Key.Key_Home:
            self.go(-len(self.shots))
        elif key == Qt.Key.Key_End:
            self.go(len(self.shots))
        else:
            super().keyPressEvent(event)

    def handle_pad(self, action: str) -> bool:
        """Controller: links/rechts blättern, A tut nichts, B (nicht behandelt) schließt."""
        if action == "left":
            self.go(-1)
        elif action == "right":
            self.go(1)
        elif action not in ("a", "up", "down", "l1", "r1"):
            return False
        return True


# ----------------------------------------------------------------------- Galerie
class ScreenshotGalleryDialog(QDialog):
    def __init__(self, data_manager, game: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.data = data_manager
        self.game = game
        self._generation = 0
        self._worker: ThumbWorker | None = None
        self._tiles: list[ThumbButton] = []
        self._shots: list[Shot] = []
        self._cols = 0

        emu_path = self.data.resolve_emulator_path(game)
        self.folder, self.tried = resolve_dir(game, emu_path)
        self.own: list[Shot] = []
        self.everything: list[Shot] = []
        if self.folder is not None:
            self.own, self.everything = find_screenshots(self.folder, game, game.get("rom_path", ""))

        self.setWindowTitle(f"Screenshots – {game['name']}")
        self.setModal(True)
        self.resize(1040, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 18)
        root.setSpacing(12)
        head = QLabel(f"📷  Screenshots – {game['name']}")
        head.setObjectName("DialogTitle")
        head.setWordWrap(True)
        root.addWidget(head)
        self.info = QLabel()
        self.info.setObjectName("HintLabel")
        self.info.setWordWrap(True)
        root.addWidget(self.info)

        toggles = QHBoxLayout()
        toggles.setSpacing(8)
        self.btn_own = QPushButton(tr("Nur dieses Spiel ({count})", count=len(self.own)))
        self.btn_all = QPushButton(tr("Alle Emulator-Screenshots ({count})", count=len(self.everything)))
        group = QButtonGroup(self)
        group.setExclusive(True)
        for b, mode in ((self.btn_own, "own"), (self.btn_all, "all")):
            b.setObjectName("FilterButton")
            b.setProperty("emu", "Alle")
            b.setCheckable(True)
            b.setAutoDefault(False)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            bold = QFont(b.font())
            bold.setBold(True)  # aktiver Zustand ist fett und braucht mehr Platz
            b.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(b.text()) + 48)
            group.addButton(b)
            toggles.addWidget(b)
            b.clicked.connect(lambda _=False, m=mode: self.set_mode(m))
        toggles.addStretch(1)
        root.addLayout(toggles)
        self.hint = QLabel()
        self.hint.setObjectName("HintLabel")
        self.hint.setWordWrap(True)
        self.hint.hide()
        root.addWidget(self.hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.container.setObjectName("LibraryContainer")
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setSpacing(GAP)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        self.empty = QLabel()
        self.empty.setObjectName("EmptyState")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setWordWrap(True)
        root.addWidget(self.empty, 1)

        foot = QHBoxLayout()
        self.btn_folder = QPushButton(tr("📂  Ordner im Explorer öffnen"))
        self.btn_folder.setEnabled(self.folder is not None)
        close = QPushButton(tr("Schließen"))
        for b in (self.btn_folder, close):
            b.setAutoDefault(False)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        foot.addWidget(self.btn_folder)
        foot.addStretch(1)
        foot.addWidget(close)
        root.addLayout(foot)
        self.btn_folder.clicked.connect(lambda: open_in_file_manager(str(self.folder), self))
        close.clicked.connect(self.reject)

        self._reflow_timer = QTimer(self, singleShot=True, interval=80)
        self._reflow_timer.timeout.connect(self._reflow)

        self._start()

    # ------------------------------------------------------------- Start
    def _start(self) -> None:
        if self.folder is None:
            self.btn_own.setEnabled(False)
            self.btn_all.setEnabled(False)
            self.info.setText(tr("Kein Screenshot-Ordner gefunden."))
            paths = "\n".join(f"• {p}" for p in self.tried) or tr("• (kein Emulator-Pfad hinterlegt)")
            self._show_empty(tr(
                "Kein Screenshot-Ordner gefunden.\n\nGeprüft:\n{paths}\n\n"
                "Tipp: Unter „Bearbeiten“ → „Screenshot-Ordner“ einen eigenen Ordner angeben.", paths=paths))
            return
        self.info.setText(tr("Ordner: {folder}", folder=self.folder))
        if not self.everything:
            self.btn_own.setEnabled(False)
            self.btn_all.setEnabled(False)
            self._show_empty(tr("Noch keine Screenshots in\n{folder}", folder=self.folder))
            return
        if self.own:
            self.set_mode("own")
        else:
            self.hint.setText(
                tr("Über Spielname/Title-ID ließ sich nichts zuordnen (viele Emulatoren benennen "
                "Screenshots nur mit Datum) – es werden alle Screenshots des Emulators gezeigt."))
            self.hint.show()
            self.set_mode("all")

    def _show_empty(self, text: str) -> None:
        self.scroll.hide()
        self.empty.setText(text)
        self.empty.show()

    # ------------------------------------------------------------ Modus
    def set_mode(self, mode: str) -> None:
        source = self.own if mode == "own" else self.everything
        (self.btn_own if mode == "own" else self.btn_all).setChecked(True)
        if mode == "own":
            self.hint.hide()
        self._shots = source[:MAX_SHOWN]
        total = len(source)
        extra = tr("  ·  zeige die neuesten {shown} von {total}", shown=MAX_SHOWN, total=total) if total > MAX_SHOWN else ""
        self.info.setText(tr("Ordner: {folder}", folder=self.folder) + extra)
        self.empty.hide()
        self.scroll.show()
        self._build_tiles()

    def _build_tiles(self) -> None:
        self._generation += 1
        if self._worker is not None:
            self._worker.requestInterruption()
        for tile in self._tiles:
            self.grid.removeWidget(tile)
            tile.deleteLater()
        self._tiles = []
        for i, shot in enumerate(self._shots):
            tile = ThumbButton(i, shot)
            tile.clicked.connect(lambda _=False, k=i: self.open_viewer(k))
            tile.navigate.connect(self._on_arrow)
            self._tiles.append(tile)
        self._cols = 0
        self._reflow()
        if self._tiles:
            self._tiles[0].setFocus()
            dpr = screen_dpr()
            self._worker = ThumbWorker([s.path for s in self._shots],
                                       QSize(int(THUMB_W * dpr), int(THUMB_H * dpr)),
                                       self._generation)
            self._worker.thumb.connect(self._on_thumb)
            self._worker.start()

    def _on_thumb(self, index: int, img: QImage, generation: int) -> None:
        if generation == self._generation and 0 <= index < len(self._tiles):
            self._tiles[index].set_image(img)

    # ------------------------------------------------------------- Raster
    def _columns(self) -> int:
        width = self.scroll.viewport().width() - 8
        return max(1, (width + GAP) // (THUMB_W + 2 * TILE_PAD + 4 + GAP))

    def _reflow(self) -> None:
        cols = self._columns()
        if cols == self._cols and self.grid.count() == len(self._tiles):
            return  # Spaltenzahl unverändert -> nichts umbauen
        self._cols = cols
        for tile in self._tiles:
            self.grid.removeWidget(tile)
        for i, tile in enumerate(self._tiles):
            self.grid.addWidget(tile, i // cols, i % cols)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reflow_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self._reflow_timer.start()

    # --------------------------------------------------------- Navigation
    def _focused_index(self) -> int:
        w = QApplication.focusWidget()
        return w.index if isinstance(w, ThumbButton) else -1

    def move_focus(self, dx: int, dy: int) -> None:
        n = len(self._tiles)
        if not n:
            return
        i = self._focused_index()
        if i < 0:
            target = 0
        elif dx:
            target = max(0, min(n - 1, i + dx))
        else:
            j = i + dy * max(1, self._cols)
            if 0 <= j < n:
                target = j
            elif dy > 0 and i // self._cols < (n - 1) // self._cols:
                target = n - 1
            else:
                target = i
        tile = self._tiles[target]
        tile.setFocus()
        self.scroll.ensureWidgetVisible(tile, 20, 20)

    def _on_arrow(self, key: int) -> None:
        dx = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}.get(Qt.Key(key), 0)
        dy = {Qt.Key.Key_Up: -1, Qt.Key.Key_Down: 1}.get(Qt.Key(key), 0)
        self.move_focus(dx, dy)

    def open_viewer(self, index: int) -> None:
        if not self._shots:
            return
        viewer = ScreenshotViewer(self._shots, index, parent=self)
        viewer.exec_maximized()
        if 0 <= viewer.index < len(self._tiles):
            self._tiles[viewer.index].setFocus()
            self.scroll.ensureWidgetVisible(self._tiles[viewer.index], 20, 20)
        viewer.deleteLater()

    def handle_pad(self, action: str) -> bool:
        """Controller: D-Pad bewegt den Fokus, A öffnet das Bild, B (nicht behandelt) schließt."""
        if action in ("left", "right", "up", "down"):
            self.move_focus({"left": -1, "right": 1}.get(action, 0), {"up": -1, "down": 1}.get(action, 0))
            return True
        if action == "a":
            i = self._focused_index()
            if i >= 0:
                self.open_viewer(i)
            return True
        return action in ("l1", "r1")

    def done(self, result: int) -> None:
        self._generation += 1          # späte Vorschauen werden ignoriert
        if self._worker is not None:
            self._worker.requestInterruption()
        super().done(result)
