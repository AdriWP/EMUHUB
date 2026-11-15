"""Screenshot-Ordner der Emulatoren finden, scannen und dem Spiel zuordnen (ohne Qt)."""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXT = (".png", ".jpg", ".jpeg")
MAX_DEPTH = 3
MAX_FILES = 5000

# Ordnername im Datenverzeichnis (%AppData%) je Emulator
APPDATA_FOLDER = {
    "Ryujinx": "Ryujinx",
    "Citra": "Citra",
    "Citron": "citron",
    "Eglantine": "Eglantine",
}
# Zusätzliche, weniger sichere Kandidaten (nur wenn die Hauptordner leer/fehlend sind)
EXTRA_APPDATA = {"Citra": ("Azahar",)}


@dataclass(frozen=True)
class Shot:
    path: Path
    mtime: float


# ----------------------------------------------------------------- Namen
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def clean_title(text: str) -> str:
    """'Super Mario Odyssey [0100…][v0] (USA)' -> 'Super Mario Odyssey'."""
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text)
    return re.sub(r"\s+", " ", text.replace("_", " ")).strip(" -.")


def title_id(*texts: str) -> str:
    """16-stellige Switch-Title-ID aus ROM-Dateiname oder Spielname ('' wenn keine)."""
    for t in texts:
        m = re.search(r"(?<![0-9A-Fa-f])(0100[0-9A-Fa-f]{12})(?![0-9A-Fa-f])", os.path.basename(t or ""))
        if m:
            return m.group(1).lower()
    return ""


# ----------------------------------------------------------- Ordnersuche
def candidate_dirs(game: dict, emulator_path: str = "") -> list[Path]:
    """Mögliche Screenshot-Ordner in Prioritätsreihenfolge.
    Eigener Pfad im Spiel gesetzt -> nur dieser."""
    custom = (game.get("screenshot_dir") or "").strip().strip('"')
    if custom:
        return [Path(custom)]
    dirs: list[Path] = []
    if emulator_path:
        exe_dir = Path(emulator_path).parent
        dirs += [exe_dir / "user" / "screenshots", exe_dir / "portable" / "screenshots"]
    appdata = os.path.expandvars(r"%AppData%")
    emu = game.get("emulator", "")
    if "%" not in appdata and appdata:  # Variable fehlt -> bleibt unverändert, überspringen
        for name in (APPDATA_FOLDER.get(emu),) + EXTRA_APPDATA.get(emu, ()):
            if name:
                dirs.append(Path(appdata) / name / "screenshots")
    return dirs


def has_images(folder: Path) -> bool:
    try:
        for _ in _walk(folder, limit=300):
            return True
    except OSError:
        pass
    return False


def resolve_dir(game: dict, emulator_path: str = "") -> tuple[Path | None, list[Path]]:
    """(gewählter Ordner, alle geprüften Ordner).
    Eigener Pfad ist exklusiv. Sonst: erster Kandidat mit Bildern; hat keiner Bilder,
    der erste vorhandene – so verdeckt ein leerer 'user\\screenshots' nicht den AppData-Ordner."""
    tried = candidate_dirs(game, emulator_path)
    if (game.get("screenshot_dir") or "").strip():
        return (tried[0] if tried[0].is_dir() else None), tried
    existing = [d for d in tried if d.is_dir()]
    for d in existing:
        if has_images(d):
            return d, tried
    return (existing[0] if existing else None), tried


# --------------------------------------------------------------- Scannen
def _walk(root: Path, limit: int = MAX_FILES):
    """Bilddateien (Tiefe und Anzahl begrenzt) als (Pfad, mtime)."""
    seen = 0
    base = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        if len(Path(dirpath).parts) - base >= MAX_DEPTH:
            dirnames[:] = []
        for fn in filenames:
            if not fn.lower().endswith(IMAGE_EXT):
                continue
            seen += 1
            if seen > limit:
                return
            p = Path(dirpath) / fn
            try:
                yield p, p.stat().st_mtime
            except OSError:
                continue


def scan(folder: Path) -> list[Shot]:
    """Alle Screenshots, neueste zuerst."""
    shots = [Shot(p, m) for p, m in _walk(folder)]
    shots.sort(key=lambda s: s.mtime, reverse=True)
    return shots


def matches_game(shot: Shot, folder: Path, name: str, tid: str) -> bool:
    """Treffer, wenn Spielname oder Title-ID in Ordner-/Dateiname (relativ zum Screenshot-Ordner) steckt."""
    try:
        rel = shot.path.relative_to(folder)
    except ValueError:
        rel = Path(shot.path.name)
    if tid and tid in str(rel).lower():
        return True
    want = normalize(clean_title(name))
    if len(want) < 3:
        return False
    parts = [normalize(p) for p in (*rel.parts[:-1], rel.stem)]
    return any(want in p for p in parts)


def find_screenshots(folder: Path, game: dict, rom_path: str = "") -> tuple[list[Shot], list[Shot]]:
    """(passend zum Spiel, alle) – beide neueste zuerst; einmal scannen, beliebig umschalten."""
    everything = scan(folder)
    tid = title_id(rom_path, game.get("name", ""))
    own = [s for s in everything if matches_game(s, folder, game.get("name", ""), tid)]
    return own, everything
