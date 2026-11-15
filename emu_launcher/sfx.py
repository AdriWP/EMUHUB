"""Soundeffekte (Blasen-„Blub“ beim Darüberfahren mit Maus oder Controller).

Ein Effekt für die ganze App: `effects()`. Lautstärke 0–100 (0 = aus), Einstellung `sfx_volume`
in games_data.json. Ohne QtMultimedia bleibt alles still (kein Fehler).
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QUrl
from PySide6.QtWidgets import QAbstractButton, QApplication

from data_manager import get_base_dir
from music import AVAILABLE, volume_to_gain

if AVAILABLE:
    from PySide6.QtMultimedia import QSoundEffect

DEFAULT_SFX_VOLUME = 50
MIN_GAP = 0.06   # Sekunden zwischen zwei Klängen (schnelles Überfahren soll nicht knattern)
SOUND_FILE = get_base_dir() / "assets" / "sounds" / "bubble.wav"   # bei der .exe: Ordner neben EMUHUB.exe


class SoundEffects(QObject):
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.volume = DEFAULT_SFX_VOLUME
        self._last = 0.0
        self._hover = None
        if AVAILABLE and SOUND_FILE.is_file():
            try:
                self._hover = QSoundEffect(self)
                self._hover.setSource(QUrl.fromLocalFile(str(SOUND_FILE)))
                self._hover.setVolume(volume_to_gain(self.volume))
            except Exception:
                self._hover = None

    @property
    def usable(self) -> bool:
        return self._hover is not None

    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, int(volume)))
        if self._hover is not None:
            self._hover.setVolume(volume_to_gain(self.volume))

    def play_hover(self, force: bool = False) -> bool:
        """Spielt den Blasen-Klang. Gibt zurück, ob ein Klang ausgelöst wurde."""
        now = time.monotonic()
        if self._hover is None or self.volume <= 0 or (not force and now - self._last < MIN_GAP):
            return False
        self._last = now
        self._hover.play()
        return True


class HoverSoundFilter(QObject):
    """Application-Filter: Maus betritt eine Kachel oder einen Knopf im Hauptfenster -> Blasen-Klang.
    Hauptfenster = Fenster mit der Eigenschaft `hover_sfx` (Dialoge bleiben still)."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Enter and (isinstance(obj, QAbstractButton) or obj.objectName() == "GameCard"):
            try:
                win = obj.window()
                if win is not None and win.property("hover_sfx") and obj.isEnabled():
                    effects().play_hover()
            except RuntimeError:
                pass
        return False


_effects: SoundEffects | None = None
_filter: HoverSoundFilter | None = None


def effects() -> SoundEffects:
    global _effects
    if _effects is None:
        _effects = SoundEffects()
    return _effects


def install(settings: dict) -> None:
    """Lautstärke aus den Einstellungen laden und den Hover-Filter einhängen (einmalig)."""
    global _filter
    try:
        volume = int(settings.get("sfx_volume", DEFAULT_SFX_VOLUME))
    except (TypeError, ValueError):
        volume = DEFAULT_SFX_VOLUME
    effects().set_volume(volume)
    if _filter is None:
        _filter = HoverSoundFilter()
        QApplication.instance().installEventFilter(_filter)
