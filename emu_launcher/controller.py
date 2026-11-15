"""Gamepad-Unterstützung über pygame.joystick (ohne Pygame-Fenster).

Der Controller liest nur Eingaben und sendet das Signal `action` mit einem der Namen
"up", "down", "left", "right", "a", "b", "l1", "r1". Was damit passiert, entscheidet
das Hauptfenster.

Tasten-Belegung (laut pygame-Dokumentation, pygame 2.x), je Gerät automatisch:
  Hat-Layout     (Xbox 360/One, PS5):         A=0, B=1, L1=4, R1=5, D-Pad = Hat 0
  Tasten-Layout  (PS4, Switch Pro, 8BitDo …): A=0, B=1, L1=9, R1=10, D-Pad = Tasten 11–14
  Linker Stick (beide): Achsen 0/1
"""
from __future__ import annotations

import math
import os
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from i18n import tr

# pygame importieren, ohne dass SDL-Umgebungsvariablen an gestartete Emulatoren
# vererbt werden (viele Emulatoren nutzen selbst SDL).
_SDL_VARS = {
    "PYGAME_HIDE_SUPPORT_PROMPT": "1",       # keine Begrüßung auf der Konsole
    "SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS": "1",  # Eingaben auch ohne SDL-Fenster
    "SDL_VIDEODRIVER": "dummy",              # SDL öffnet kein Fenster, ändert kein DPI
}


def _with_sdl_env(func: Callable):
    """Führt func mit gesetzten SDL-Variablen aus und stellt die Umgebung danach wieder her."""
    saved = {k: os.environ.get(k) for k in _SDL_VARS}
    for key, value in _SDL_VARS.items():
        os.environ.setdefault(key, value)
    try:
        return func()
    finally:
        for key, old in saved.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old


try:
    pygame = _with_sdl_env(lambda: __import__("pygame"))
except Exception:  # ImportError oder kaputte Installation
    pygame = None

LAYOUT_HAT = {"a": 0, "b": 1, "l1": 4, "r1": 5, "dpad": {}}
LAYOUT_BUTTONS = {"a": 0, "b": 1, "l1": 9, "r1": 10,
                  "dpad": {11: "up", 12: "down", 13: "left", 14: "right"}}
FACE_ACTIONS = ("a", "b", "l1", "r1")
DEADZONE = 0.5
REPEAT_DELAY = 0.35   # Sekunden bis zur ersten Wiederholung beim Halten
REPEAT_RATE = 0.12    # danach alle 120 ms


class GamepadController(QObject):
    action = Signal(str)
    status = Signal(str)

    def __init__(self, gate: Callable[[], bool] | None = None, interval_ms: int = 50,
                 backend=None, parent: QObject | None = None):
        """gate: gibt True zurück, wenn Eingaben verarbeitet werden dürfen (Fenster aktiv).
        backend: nur für Tests (Ersatz für das pygame-Modul)."""
        super().__init__(parent)
        self._pg = backend if backend is not None else pygame
        self._gate = gate or (lambda: True)
        self._joys: dict[int, object] = {}        # instance_id -> Joystick
        self._layouts: dict[int, dict] = {}       # instance_id -> Tasten-Layout
        self._prev_buttons: set[str] = set()
        self._dir_next: dict[str, float] = {}     # Richtung -> nächster Auslösezeitpunkt
        self._polling = False
        self._started = False
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.poll)

    # ------------------------------------------------------------ Lebenszyklus
    @property
    def available(self) -> bool:
        return self._pg is not None

    @property
    def connected(self) -> int:
        return len(self._joys)

    def start(self) -> bool:
        if self._pg is None:
            self.status.emit(tr("Controller-Steuerung aus: pygame fehlt (pip install pygame-ce)"))
            return False
        try:
            # Video-Subsystem ist für event.get() nötig, mit dummy-Treiber ohne Fenster
            _with_sdl_env(lambda: (self._pg.display.init(), self._pg.joystick.init()))
            for index in range(self._pg.joystick.get_count()):
                self._open(index)
        except Exception as exc:
            self.status.emit(tr("Controller-Steuerung nicht verfügbar: {exc}", exc=exc))
            self._pg = None
            return False
        self._started = True
        self._timer.start()
        return True

    def stop(self) -> None:
        self._timer.stop()
        self._joys.clear()
        self._layouts.clear()
        if self._pg is not None and self._started:
            try:
                self._pg.quit()
            except Exception:
                pass
        self._started = False

    # --------------------------------------------------------------- Geräte
    def _open(self, device_index: int) -> None:
        try:
            joy = self._pg.joystick.Joystick(device_index)
            iid = joy.get_instance_id()
        except Exception:
            return
        if iid in self._joys:  # JOYDEVICEADDED kommt auch für schon verbundene Geräte
            return
        self._joys[iid] = joy
        # Ohne Hat, aber mit ≥ 15 Tasten: D-Pad liegt auf Tasten (PS4, Switch Pro, 8BitDo …)
        no_hat = joy.get_numhats() == 0 and joy.get_numbuttons() >= 15
        self._layouts[iid] = LAYOUT_BUTTONS if no_hat else LAYOUT_HAT
        self.status.emit(tr("🎮 Controller verbunden: {name}", name=joy.get_name()))

    def _close(self, instance_id: int) -> None:
        self._layouts.pop(instance_id, None)
        if self._joys.pop(instance_id, None) is not None:
            self.status.emit(tr("🎮 Controller getrennt"))

    # --------------------------------------------------------------- Abfrage
    def poll(self) -> None:
        """Wird alle 50 ms aufgerufen. Zustände werden immer aktualisiert, Aktionen
        aber nur gesendet, wenn das Fenster aktiv ist (sonst würden Tasten, die im
        Emulator gedrückt werden, beim Zurückwechseln als neuer Druck zählen)."""
        if self._pg is None or self._polling:
            return
        self._polling = True
        try:
            pg = self._pg
            for ev in pg.event.get():
                if ev.type == pg.JOYDEVICEADDED:
                    self._open(ev.device_index)
                elif ev.type == pg.JOYDEVICEREMOVED:
                    self._close(ev.instance_id)

            buttons: set[str] = set()
            directions: set[str] = set()
            for iid, joy in list(self._joys.items()):
                lay = self._layouts.get(iid, LAYOUT_HAT)
                try:
                    count = joy.get_numbuttons()
                    for name in FACE_ACTIONS:
                        if lay[name] < count and joy.get_button(lay[name]):
                            buttons.add(name)
                    for idx, direction in lay["dpad"].items():
                        if idx < count and joy.get_button(idx):
                            directions.add(direction)
                    if joy.get_numhats() > 0:
                        hx, hy = joy.get_hat(0)
                        if hx:
                            directions.add("right" if hx > 0 else "left")
                        if hy:
                            directions.add("up" if hy > 0 else "down")
                    if joy.get_numaxes() >= 2:
                        ax, ay = joy.get_axis(0), joy.get_axis(1)
                        if max(abs(ax), abs(ay)) > DEADZONE:  # dominante Achse
                            if abs(ax) >= abs(ay):
                                directions.add("right" if ax > 0 else "left")
                            else:
                                directions.add("down" if ay > 0 else "up")
                except pg.error:
                    continue  # Gerät wurde gerade abgezogen

            pressed = buttons - self._prev_buttons
            self._prev_buttons = buttons
            now = time.monotonic()
            active = bool(self._gate())

            if not active:
                # Gehaltene Richtungen merken, aber nichts senden und nach dem
                # Zurückwechseln nicht sofort wiederholen.
                self._dir_next = {d: math.inf for d in directions}
                return

            for name in sorted(pressed):
                self.action.emit(name)
            for d in sorted(directions):
                due = self._dir_next.get(d)
                if due is None:
                    self.action.emit(d)
                    self._dir_next[d] = now + REPEAT_DELAY
                elif now >= due:
                    self.action.emit(d)
                    self._dir_next[d] = now + REPEAT_RATE
            for d in list(self._dir_next):
                if d not in directions:
                    del self._dir_next[d]
        finally:
            self._polling = False
