"""Hintergrundmusik (MP3 u. a.) für EMUHUB – eine Endlosschleife, Lautstärke sofort änderbar.

Nutzt Qt Multimedia (Teil von `PySide6`; fehlt es, bleibt die Funktion einfach abgeschaltet).
Ein einziger Player für die ganze App: `player()`. Einstellungen (settings in games_data.json):
  music_file (Pfad), music_enabled (bool), music_volume (0–100)
"""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, QUrl, Signal

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    AVAILABLE = True
except Exception:   # QtMultimedia nicht installiert
    QAudioOutput = QMediaPlayer = None
    AVAILABLE = False

AUDIO_EXTENSIONS = "*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.wma"
DEFAULT_VOLUME = 40


def volume_to_gain(volume: int) -> float:
    """Regler 0–100 -> Qt-Lautstärke 0.0–1.0. Quadratisch, weil wir Lautstärke ungefähr logarithmisch hören
    (sonst ist die untere Hälfte des Reglers kaum zu unterscheiden)."""
    v = max(0, min(100, int(volume))) / 100
    return v * v


class MusicPlayer(QObject):
    state_changed = Signal()   # Wiedergabe gestartet/gestoppt/Fehler -> Anzeige aktualisieren

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.path = ""
        self.enabled = False
        self.volume = DEFAULT_VOLUME
        self.error = ""
        self._player = self._audio = None
        if AVAILABLE:
            try:
                self._audio = QAudioOutput(self)
                self._player = QMediaPlayer(self)
                self._player.setAudioOutput(self._audio)
                self._player.setLoops(QMediaPlayer.Loops.Infinite)
                self._player.errorOccurred.connect(self._on_error)
                self._player.playbackStateChanged.connect(lambda *_: self.state_changed.emit())
                self._audio.setVolume(volume_to_gain(self.volume))
            except Exception:
                self._player = self._audio = None

    # ------------------------------------------------------------------ Status
    @property
    def usable(self) -> bool:
        return self._player is not None

    @property
    def playing(self) -> bool:
        return self.usable and self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def file_exists(self) -> bool:
        return bool(self.path) and os.path.isfile(self.path)

    # --------------------------------------------------------------- Steuerung
    def configure(self, path: str, enabled: bool, volume: int) -> None:
        """Alles auf einmal setzen (beim Start / nach Änderungen)."""
        self.volume = max(0, min(100, int(volume)))
        if self.usable:
            self._audio.setVolume(volume_to_gain(self.volume))
        self.set_file(path, enabled)

    def set_volume(self, volume: int) -> None:
        """Wirkt sofort auf die laufende Wiedergabe."""
        self.volume = max(0, min(100, int(volume)))
        if self.usable:
            self._audio.setVolume(volume_to_gain(self.volume))

    def set_file(self, path: str, enabled: bool) -> None:
        path = (path or "").strip().strip('"')
        changed = path != self.path
        self.path, self.enabled, self.error = path, bool(enabled), ""
        if not self.usable:
            self.state_changed.emit()
            return
        if changed:
            self._player.stop()
            self._player.setSource(QUrl.fromLocalFile(path) if path else QUrl())
        self._apply_enabled()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self._apply_enabled()

    def _apply_enabled(self) -> None:
        if not self.usable:
            return
        if self.enabled and self.file_exists():
            self._player.play()
        else:
            self._player.pause() if self.file_exists() else self._player.stop()
        self.state_changed.emit()

    def stop(self) -> None:
        if self.usable:
            self._player.stop()

    def _on_error(self, _error, message: str = "") -> None:
        self.error = message or "error"
        self.state_changed.emit()


_player: MusicPlayer | None = None


def player() -> MusicPlayer:
    """Der eine Player der App (wird beim ersten Aufruf angelegt; QApplication muss existieren)."""
    global _player
    if _player is None:
        _player = MusicPlayer()
    return _player


def apply_settings(settings: dict) -> None:
    """Liest die Musik-Einstellungen aus games_data.json und startet/stoppt die Wiedergabe entsprechend."""
    try:
        volume = int(settings.get("music_volume", DEFAULT_VOLUME))
    except (TypeError, ValueError):
        volume = DEFAULT_VOLUME
    player().configure(settings.get("music_file", ""), bool(settings.get("music_enabled", True)), volume)
