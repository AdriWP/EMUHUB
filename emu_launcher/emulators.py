"""Emulator-Einrichtung: Programm erkennen, Status prüfen, Datenordner finden.

Bewusst NICHT enthalten: Änderungen an den Konfigurationsdateien der Emulatoren selbst
(Grafik, Controller, Firmware, Schlüssel stellt man im Emulator ein – EMUHUB öffnet ihn dafür).
Die Programmnamen von Citron und Eglantine sind nicht verifiziert; gesucht wird nach dem Namenspräfix.
"""
from __future__ import annotations

import ctypes
import os
import string
from collections import deque
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from screenshots import APPDATA_FOLDER, EXTRA_APPDATA

# Dateinamen-Präfixe der Programme (klein geschrieben)
EXE_PREFIXES: dict[str, tuple[str, ...]] = {
    "Ryujinx": ("ryujinx",),
    "Citra": ("citra", "azahar"),
    "Citron": ("citron",),
    "Eglantine": ("eglantine",),
}
IGNORE_IN_NAME = ("updater", "uninstall", "unins", "maintenance", "crash", "vcredist", "setup", "installer")
LOW_PRIORITY = ("room", "cmd", "cli", "server")          # Nebenprogramme: weiter hinten einsortieren
SKIP_DIRS = {"windows", "windowsapps", "$recycle.bin", "node_modules", ".git",
             "system volume information", "temp", "cache", "shader", "shaders"}
EXTRA_FOLDERS = ("Emulatoren", "Emulators", "Emulator", "Games", "Spiele")
MAX_DEPTH = 4
MAX_DIRS_PER_ROOT = 2500
MAX_RESULTS = 20


def exe_status(path: str) -> str:
    """'none' = kein Pfad, 'missing' = Datei fehlt, 'ok' = Datei vorhanden."""
    path = (path or "").strip().strip('"')
    if not path:
        return "none"
    return "ok" if os.path.isfile(path) else "missing"


# ------------------------------------------------------------------ Datenordner
def data_dir_candidates(emulator: str, exe_path: str = "") -> list[tuple[Path, str]]:
    """Mögliche Datenordner (Pfad, Art). Portabel (neben der .exe) zuerst, dann %AppData%."""
    out: list[tuple[Path, str]] = []
    exe_path = (exe_path or "").strip().strip('"')
    if exe_path:
        exe_dir = Path(exe_path).parent
        out += [(exe_dir / "user", "portable"), (exe_dir / "portable", "portable")]
    appdata = os.path.expandvars(r"%AppData%")
    if appdata and "%" not in appdata:   # Variable fehlt -> bleibt unverändert, überspringen
        for name in (APPDATA_FOLDER.get(emulator),) + EXTRA_APPDATA.get(emulator, ()):
            if name:
                out.append((Path(appdata) / name, "appdata"))
    return out


def find_data_dir(emulator: str, exe_path: str = "") -> tuple[tuple[Path, str] | None, list[Path]]:
    """((Pfad, Art) des ersten vorhandenen Datenordners | None, alle geprüften Pfade). Legt nie etwas an."""
    cands = data_dir_candidates(emulator, exe_path)
    for path, kind in cands:
        if path.is_dir():
            return (path, kind), [p for p, _ in cands]
    return None, [p for p, _ in cands]


# ----------------------------------------------------------------- Programmsuche
def fixed_drives(get_mask=None, get_type=None) -> str:
    """Buchstaben vorhandener Festplatten/Wechseldatenträger (Windows). Netzlaufwerke und leere
    optische Laufwerke werden bewusst ausgelassen – sie können beim Zugriff lange blockieren."""
    if get_mask is None:
        if os.name != "nt":
            return ""
        try:
            kernel32 = ctypes.windll.kernel32
            get_mask, get_type = kernel32.GetLogicalDrives, kernel32.GetDriveTypeW
        except Exception:
            return ""
    try:
        mask = get_mask()
        return "".join(letter for i, letter in enumerate(string.ascii_uppercase)
                       if mask & (1 << i) and get_type(letter + ":" + chr(92)) in (2, 3))   # 2 = Wechsel-, 3 = Festplatte
    except Exception:
        return ""


def default_search_roots(drives: str | None = None) -> list[Path]:
    """Übliche Orte, nur aus Umgebungsvariablen und festen Namen – nichts wird erraten.
    `drives`: Laufwerksbuchstaben für Ordner wie X:/Emulatoren (None = vorhandene Festplatten)."""
    if drives is None:
        drives = fixed_drives()
    env = os.environ
    candidates: list[Path] = []
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        if env.get(var):
            candidates.append(Path(env[var]))
    if env.get("LOCALAPPDATA"):
        candidates.append(Path(env["LOCALAPPDATA"]) / "Programs")
    if env.get("APPDATA"):
        candidates.append(Path(env["APPDATA"]))
    if env.get("USERPROFILE"):
        candidates += [Path(env["USERPROFILE"]) / sub for sub in ("Desktop", "Downloads", "Documents")]
    for letter in drives:
        candidates += [Path(letter + ":/" + folder) for folder in EXTRA_FOLDERS]
    roots, seen = [], set()
    for c in candidates:
        key = str(c).lower()
        if key not in seen and c.is_dir():
            seen.add(key)
            roots.append(c)
    return roots


def _rank(path: Path) -> tuple[int, float]:
    stem = path.stem.lower()
    low = any(w in stem for w in LOW_PRIORITY)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (1 if low else 0, -mtime)


def find_exes(emulator: str, roots: list[Path], *, max_depth: int = MAX_DEPTH,
              max_dirs: int = MAX_DIRS_PER_ROOT, should_stop=lambda: False) -> list[Path]:
    """Sucht passende .exe-Dateien – breitenweise (flache Ordner zuerst), je Wurzel mit Budget an
    Ordnern. So erreicht die Suche z. B. Program Files\\Ryujinx auch dann, wenn daneben riesige
    Ordner liegen. Updater/Installer werden ignoriert, Nebenprogramme (-room, -cmd) kommen nach hinten."""
    prefixes = EXE_PREFIXES.get(emulator, (emulator.lower(),))
    found: dict[str, Path] = {}
    for root in roots:
        queue = deque([(root, 0)])
        visited = 0
        while queue:
            if should_stop():
                return sorted(found.values(), key=_rank)[:MAX_RESULTS]
            folder, depth = queue.popleft()
            visited += 1
            if visited > max_dirs:
                break
            try:
                entries = list(os.scandir(folder))
            except OSError:
                continue
            for entry in entries:
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                low = entry.name.lower()
                if is_dir:
                    if depth < max_depth and low not in SKIP_DIRS:
                        queue.append((Path(entry.path), depth + 1))
                elif low.endswith(".exe"):
                    stem = low[:-4]
                    if any(stem.startswith(p) for p in prefixes) and not any(w in stem for w in IGNORE_IN_NAME):
                        found.setdefault(entry.path.lower(), Path(entry.path))
    return sorted(found.values(), key=_rank)[:MAX_RESULTS]


class ExeSearchWorker(QThread):
    """Sucht im Hintergrund. Ergebnis: Signal found(emulator, [Pfade als Text])."""
    found = Signal(str, list)
    _active: set = set()   # starke Referenz bis der Thread beendet ist

    def __init__(self, emulator: str, roots: list[Path] | None = None):
        super().__init__()  # ohne Parent: überlebt das Schließen des Dialogs
        self._emulator = emulator
        self._roots = roots
        ExeSearchWorker._active.add(self)
        self.finished.connect(self._release)

    @classmethod
    def wait_all(cls, timeout_ms: int = 3000) -> None:
        for w in list(cls._active):
            w.requestInterruption()
            w.wait(timeout_ms)

    def _release(self) -> None:
        ExeSearchWorker._active.discard(self)   # kein deleteLater(): der Dialog hält den Thread noch

    def run(self) -> None:
        try:
            roots = self._roots if self._roots is not None else default_search_roots()
            paths = find_exes(self._emulator, roots, should_stop=self.isInterruptionRequested)
        except Exception:
            paths = []
        self.found.emit(self._emulator, [str(p) for p in paths])
