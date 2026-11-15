"""Datenschicht: Laden/Speichern von games_data.json, Cover-Import und Startbefehl."""
from __future__ import annotations

import json
import os
import shlex
import sys
import uuid
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QImageReader

from i18n import tr

# Fest eingebaute Emulatoren: bewusst leer – EMUHUB startet ohne vorgegebene Emulatoren,
# jeder Nutzer legt seine eigenen an (Einstellungen -> Emulatoren). Die Logik bleibt für eingebaute Einträge erhalten.
BUILTIN_EMULATORS: dict[str, str] = {}
# Alle bekannten Emulatoren (eingebaute + eigene). Wird NUR vorhanden verändert (nie neu zugewiesen),
# damit alle Module, die `EMULATORS` importiert haben, Änderungen sehen. Pflegt `DataManager`.
EMULATORS: dict[str, str] = dict(BUILTIN_EMULATORS)

MAX_EMULATOR_NAME = 24


# Kachel-Cover-Größe (logische Pixel). Gespeichert wird in doppelter Auflösung.
CARD_COVER_W = 180
CARD_COVER_H = 240

SWITCH_EXT = (".nsp", ".xci", ".nca", ".nro", ".nso")
N3DS_EXT = (".3ds", ".cia", ".cci", ".cxi", ".3dsx", ".app")

def rom_filter() -> str:
    """Dateifilter für ROMs (Text je nach Sprache, daher Funktion statt Konstante)."""
    return (
        f"{tr('Spiele-ROMs')} (*.nsp *.xci *.nca *.nro *.nso *.3ds *.cia *.cci *.cxi *.3dsx *.app);;"
        "Switch (*.nsp *.xci *.nca *.nro *.nso);;"
        "3DS (*.3ds *.cia *.cci *.cxi *.3dsx *.app);;"
        f"{tr('Alle Dateien')} (*)"
    )


def image_filter() -> str:
    return f"{tr('Bilder')} (*.png *.jpg *.jpeg *.webp *.bmp);;{tr('Alle Dateien')} (*)"


def exe_filter() -> str:
    if os.name == "nt":
        return f"{tr('Programme')} (*.exe);;{tr('Alle Dateien')} (*)"
    return f"{tr('Alle Dateien')} (*)"


def get_base_dir() -> Path:
    """Projektordner (bzw. Ordner der .exe, falls mit PyInstaller gebaut)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def split_args(arg_string: str) -> list[str]:
    """Zerlegt Start-Argumente wie eine Shell. Unter Windows bleiben Backslashes erhalten."""
    if not arg_string or not arg_string.strip():
        return []
    posix = os.name != "nt"
    parts = shlex.split(arg_string, posix=posix)
    if not posix:
        cleaned = []
        for p in parts:
            if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'":
                p = p[1:-1]
            cleaned.append(p)
        parts = cleaned
    return parts


def same_path(a: str, b: str) -> bool:
    """Gleicher Pfad (Groß-/Kleinschreibung und Schreibweise egal, leer ist nie gleich)."""
    if not a or not b:
        return False
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def build_command(emulator_path: str, arg_string: str, rom_path: str) -> list[str]:
    """Baut den Startbefehl. '{rom}' in den Argumenten wird durch den ROM-Pfad ersetzt,
    sonst wird der ROM-Pfad ans Ende angehängt."""
    parts = split_args(arg_string)
    has_placeholder = any("{rom}" in p for p in parts)
    parts = [p.replace("{rom}", rom_path) for p in parts]
    if not has_placeholder and rom_path:
        parts.append(rom_path)
    return [emulator_path, *parts]


def is_square_cover(emulator: str, rom_path: str = "") -> bool:
    """3DS-Spiele haben quadratische Icons, Switch-Spiele Hochformat-Cover."""
    ext = os.path.splitext(rom_path or "")[1].lower()
    if ext in N3DS_EXT:
        return True
    if ext in SWITCH_EXT:
        return False
    return emulator == "Citra"


# Kachelformat pro Spiel
COVER_SHAPES: dict[str, str] = {
    "auto": "Automatisch (ganzes Bild, passt sich an)",
    "portrait": "Hochformat (3:4)",
    "square": "Quadratisch (1:1)",
}

# Extrem breite/schmale Bilder werden auf dieses Seitenverhältnis begrenzt
MIN_ASPECT = 0.55
MAX_ASPECT = 1.5


def image_ratio(path: str) -> float | None:
    """Liest nur den Bild-Header (schnell) und gibt Breite/Höhe zurück."""
    if not path or not os.path.isfile(path):
        return None
    size = QImageReader(path).size()
    if not size.isValid() or size.height() <= 0:
        return None
    return size.width() / size.height()


def cover_aspect(game: dict, cover_path: str = "") -> float:
    """Seitenverhältnis (Breite/Höhe) der Kachel. Alle Kacheln sind gleich hoch,
    nur die Breite passt sich an:
      auto     -> genau das Format des gewählten Bildes (nichts wird abgeschnitten)
      portrait -> 3:4,  square -> 1:1
    Ohne Bild: 3DS quadratisch, Switch Hochformat."""
    shape = game.get("cover_shape", "auto")
    if shape == "square":
        return 1.0
    if shape == "portrait":
        return 0.75
    ratio = image_ratio(cover_path)
    if ratio is not None:
        return min(MAX_ASPECT, max(MIN_ASPECT, ratio))
    return 1.0 if is_square_cover(game.get("emulator", ""), game.get("rom_path", "")) else 0.75


# Sortierung der Bibliothek: Schlüssel -> Anzeigetext
SORT_MODES: dict[str, str] = {
    "name": "Name (A–Z)",
    "name_desc": "Name (Z–A)",
    "last_played": "Zuletzt gespielt",
    "most_played": "Meistgespielt",
    "added": "Zuletzt hinzugefügt",
    "emulator": "Emulator",
}


def sort_games(games: list[dict], mode: str, favorites_first: bool = True) -> list[dict]:
    """Sortiert Spiele. Favoriten stehen (optional) immer oben; bei Gleichstand
    entscheidet der Name."""
    result = sorted(games, key=lambda g: g["name"].lower())
    if mode == "name_desc":
        result.reverse()
    elif mode == "last_played":
        # nie gespielte ("") landen dank stabiler Sortierung am Ende
        result.sort(key=lambda g: g.get("last_played") or "", reverse=True)
    elif mode == "most_played":
        result.sort(key=lambda g: g.get("play_count", 0), reverse=True)
    elif mode == "added":
        result.sort(key=lambda g: g.get("added") or "", reverse=True)
    elif mode == "emulator":
        order = list(EMULATORS)
        result.sort(key=lambda g: order.index(g["emulator"]) if g["emulator"] in order else 99)
    if favorites_first:
        result.sort(key=lambda g: not g.get("favorite", False))
    return result


def guess_emulator_for_rom(rom_path: str) -> str | None:
    """Passenden eigenen Emulator vermuten (nur wenn einer mit dem Namen Citra bzw. Ryujinx existiert)."""
    ext = os.path.splitext(rom_path)[1].lower()
    wanted = "citra" if ext in N3DS_EXT else "ryujinx" if ext in SWITCH_EXT else None
    return next((n for n in EMULATORS if n.lower() == wanted), None) if wanted else None


class DataManager:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.data_file = self.base_dir / "games_data.json"
        self.covers_dir = self.base_dir / "covers"
        self.covers_dir.mkdir(parents=True, exist_ok=True)
        self.backgrounds_dir = self.base_dir / "backgrounds"
        self.games: list[dict] = []
        self.custom_emulators: dict[str, str] = {}   # eigene Emulatoren: Name -> Farbe
        self.emulator_colors: dict[str, str] = {}    # vom Nutzer geänderte Farben eingebauter Emulatoren
        self.emulators: dict[str, str] = {}
        self.emulator_args: dict[str, str] = {}      # Standard-Argumente je Emulator
        self._sync_emulators()
        self.settings: dict = {}
        self.load()

    # ------------------------------------------------------- eigene Emulatoren
    def _sync_emulators(self) -> None:
        """Gleicht EMULATORS (global) und die Pfad-/Argument-Tabellen mit den eigenen Emulatoren ab."""
        EMULATORS.clear()
        EMULATORS.update(BUILTIN_EMULATORS)
        EMULATORS.update(self.custom_emulators)
        for name, color in self.emulator_colors.items():
            if name in BUILTIN_EMULATORS:
                EMULATORS[name] = color
        for table in (self.emulators, self.emulator_args):
            for name in EMULATORS:
                table.setdefault(name, "")
            for name in [n for n in table if n not in EMULATORS]:
                del table[name]

    def validate_emulator_name(self, name: str) -> str | None:
        """None = Name ist frei, sonst der Grund (Text für den Nutzer)."""
        name = (name or "").strip()
        if not name:
            return tr("Bitte einen Namen eingeben.")
        if len(name) > MAX_EMULATOR_NAME:
            return tr("Der Name ist zu lang (max. {n} Zeichen).", n=MAX_EMULATOR_NAME)
        if any(name.lower() == n.lower() for n in EMULATORS):
            return tr("Einen Emulator mit diesem Namen gibt es schon.")
        return None

    def set_emulator_colors(self, changes: dict[str, str]) -> None:
        """Farben setzen (eigene Emulatoren direkt, eingebaute als Abweichung vom Standard).
        Ungültige Farben werden ignoriert; die Standardfarbe löscht die Abweichung. Speichert nicht selbst."""
        for name, color in changes.items():
            if name not in EMULATORS or not QColor(color).isValid():
                continue
            color = QColor(color).name()
            if name in self.custom_emulators:
                self.custom_emulators[name] = color
            elif color == BUILTIN_EMULATORS.get(name):
                self.emulator_colors.pop(name, None)
            else:
                self.emulator_colors[name] = color
        self._sync_emulators()

    def apply_custom_emulators(self, added: dict[str, str], removed: set[str]) -> None:
        """Legt eigene Emulatoren an (Name -> Farbe) bzw. entfernt sie. Eingebaute bleiben immer.
        Ein Emulator, den noch Spiele nutzen, wird nicht entfernt. Speichert nicht selbst."""
        used = {g.get("emulator") for g in self.games}
        for name in removed:
            if name in self.custom_emulators and name not in used:
                del self.custom_emulators[name]
        for name, color in added.items():
            if name not in EMULATORS and not self.validate_emulator_name(name):
                self.custom_emulators[name.strip()] = color if QColor(color).isValid() else "#6b7280"
        self._sync_emulators()

    # ------------------------------------------------------------------ I/O
    def load(self) -> None:
        if not self.data_file.exists():
            self.save()
            return
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError):
            # Kaputte Datei sichern statt sie zu überschreiben
            backup = self.data_file.with_suffix(
                f".broken-{datetime.now():%Y%m%d-%H%M%S}.json"
            )
            try:
                self.data_file.replace(backup)
            except OSError:
                pass
            self.save()
            return

        self.custom_emulators = {}
        custom = raw.get("custom_emulators")
        for name, color in (custom.items() if isinstance(custom, dict) else []):
            name = str(name).strip()
            if name and name.lower() not in {n.lower() for n in BUILTIN_EMULATORS}:
                self.custom_emulators[name] = color if isinstance(color, str) and QColor(color).isValid() else "#6b7280"
        self.emulator_colors = {}
        colors = raw.get("emulator_colors")
        for name, color in (colors.items() if isinstance(colors, dict) else []):
            if name in BUILTIN_EMULATORS and isinstance(color, str) and QColor(color).isValid():
                self.emulator_colors[name] = QColor(color).name()
        self._sync_emulators()
        for name, path in (raw.get("emulators") or {}).items():
            if name in EMULATORS:
                self.emulators[name] = path or ""
        for name, args in (raw.get("emulator_args") or {}).items():
            if name in EMULATORS:
                self.emulator_args[name] = args or ""
        self.settings = dict(raw.get("settings") or {})
        self.games = []
        for g in raw.get("games") or []:
            if isinstance(g, dict):
                self.games.append(self._normalize(g))

    def save(self) -> None:
        payload = {"version": 1, "settings": self.settings, "custom_emulators": self.custom_emulators,
                   "emulator_colors": self.emulator_colors,
                   "emulators": self.emulators, "emulator_args": self.emulator_args,
                   "games": self.games}
        tmp = self.data_file.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.data_file)

    @staticmethod
    def _normalize(g: dict) -> dict:
        return {
            "id": g.get("id") or uuid.uuid4().hex,
            "name": g.get("name", "Unbenannt"),
            "cover": g.get("cover", ""),
            "rom_path": g.get("rom_path", ""),
            "emulator": g.get("emulator", ""),
            "emulator_path": g.get("emulator_path", ""),
            "args": g.get("args", ""),
            "notes": g.get("notes", ""),
            "mod_path": g.get("mod_path", ""),
            "screenshot_dir": g.get("screenshot_dir", ""),
            "cover_shape": g.get("cover_shape", "auto"),
            "last_played": g.get("last_played", ""),
            "play_count": int(g.get("play_count", 0) or 0),
            "favorite": bool(g.get("favorite", False)),
            "added": g.get("added", ""),
        }

    # ---------------------------------------------------------------- Spiele
    def get_game(self, game_id: str) -> dict | None:
        return next((g for g in self.games if g["id"] == game_id), None)

    def add_game(self, data: dict) -> dict:
        game = self._normalize({
            **data, "id": uuid.uuid4().hex,
            "added": datetime.now().isoformat(timespec="seconds"),
        })
        self.games.append(game)
        self._remember_emulator(game)
        self.save()
        return game

    def update_game(self, game_id: str, data: dict) -> dict | None:
        game = self.get_game(game_id)
        if game is None:
            return None
        old_cover = game.get("cover", "")
        game.update({k: v for k, v in data.items() if k != "id"})
        if old_cover and old_cover != game.get("cover"):
            self.remove_cover(old_cover)
        self._remember_emulator(game)
        self.save()
        return game

    def delete_game(self, game_id: str) -> None:
        game = self.get_game(game_id)
        if game is None:
            return
        self.games.remove(game)
        if game.get("cover"):
            self.remove_cover(game["cover"])
        self.save()

    def toggle_favorite(self, game_id: str) -> bool:
        """Schaltet den Favoriten-Status um und gibt den neuen Status zurück."""
        game = self.get_game(game_id)
        if game is None:
            return False
        game["favorite"] = not game.get("favorite", False)
        self.save()
        return game["favorite"]

    def mark_played(self, game_id: str) -> None:
        game = self.get_game(game_id)
        if game:
            game["last_played"] = datetime.now().isoformat(timespec="seconds")
            game["play_count"] = int(game.get("play_count", 0)) + 1
            self.save()

    def _remember_emulator(self, game: dict) -> None:
        """Merkt sich den Pfad als Standard, falls für diesen Emulator noch keiner gesetzt ist.
        Entspricht der Pfad des Spiels dem Standard, wird er im Spiel leer gespeichert – so gilt
        später immer der aktuelle Standard (Emulator verschoben = nur eine Stelle ändern)."""
        path = game.get("emulator_path", "")
        emu = game["emulator"]
        if path and not self.emulators.get(emu):
            self.emulators[emu] = path
        if path and same_path(path, self.emulators.get(emu, "")):
            game["emulator_path"] = ""

    def set_emulator_paths(self, paths: dict[str, str]) -> None:
        self.emulators.update(paths)
        self.save()

    def set_emulator_config(self, paths: dict[str, str], args: dict[str, str],
                            apply_to_games: set[str] | None = None) -> int:
        """Speichert Standardpfade und Standard-Argumente. Für Emulatoren in `apply_to_games` werden
        die eigenen Pfade aller Spiele entfernt (ab jetzt gilt der Standard). Gibt die Zahl der geänderten Spiele zurück."""
        self.emulators.update(paths)
        self.emulator_args.update(args)
        # ohne Standardpfad würde das Entfernen der eigenen Pfade Spiele unstartbar machen
        targets = {n for n in (apply_to_games or set()) if self.emulators.get(n)}
        changed = 0
        for g in self.games:
            if g.get("emulator") in targets and g.get("emulator_path"):
                g["emulator_path"] = ""
                changed += 1
        self.save()
        return changed

    def resolve_emulator_path(self, game: dict) -> str:
        return game.get("emulator_path") or self.emulators.get(game.get("emulator", ""), "")

    def resolve_args(self, game: dict) -> str:
        """Eigene Start-Argumente des Spiels, sonst die Standard-Argumente des Emulators."""
        own = (game.get("args") or "").strip()
        return own or self.emulator_args.get(game.get("emulator", ""), "").strip()

    # ---------------------------------------------------------------- Cover
    def abs_path(self, rel: str) -> str:
        if not rel:
            return ""
        p = Path(rel)
        return str(p if p.is_absolute() else self.base_dir / p)

    def set_setting(self, key: str, value) -> None:
        self.settings[key] = value
        self.save()

    def import_cover(self, source: str) -> str:
        """Kopiert ein Bild verkleinert (Seitenverhältnis bleibt erhalten) nach covers/
        und gibt den relativen Pfad zurück. Zugeschnitten wird erst beim Anzeigen –
        so kann das Kachelformat (Hochformat/Quadratisch) jederzeit gewechselt werden."""
        img = QImage(source)
        if img.isNull():
            raise ValueError(tr("Bild konnte nicht geladen werden:\n{path}", path=source))
        target_short = CARD_COVER_H * 2  # kürzere Seite 480 px – reicht für beide Formate
        short = min(img.width(), img.height())
        if short > target_short:
            img = img.scaled(
                img.width() * target_short // short, img.height() * target_short // short,
                Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
            )
        filename = f"{uuid.uuid4().hex}.png"
        target = self.covers_dir / filename
        if not img.save(str(target), "PNG"):
            raise ValueError(tr("Cover konnte nicht gespeichert werden:\n{path}", path=target))
        return f"covers/{filename}"

    def remove_cover(self, rel: str) -> None:
        self._remove_in(rel, self.covers_dir)

    # ----------------------------------------------------------- Hintergrund
    def import_background(self, source: str) -> str:
        """Kopiert ein Hintergrundbild (max. 2560 px breit) nach backgrounds/."""
        img = QImage(source)
        if img.isNull():
            raise ValueError(tr("Bild konnte nicht geladen werden:\n{path}", path=source))
        if img.width() > 2560:
            img = img.scaledToWidth(2560, Qt.TransformationMode.SmoothTransformation)
        self.backgrounds_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}.jpg"
        target = self.backgrounds_dir / filename
        if not img.save(str(target), "JPG", 92):
            raise ValueError(tr("Hintergrund konnte nicht gespeichert werden:\n{path}", path=target))
        return f"backgrounds/{filename}"

    def remove_background(self, rel: str) -> None:
        self._remove_in(rel, self.backgrounds_dir)

    def _remove_in(self, rel: str, folder: Path) -> None:
        """Löscht nur Dateien, die wirklich im angegebenen App-Ordner liegen."""
        if not rel:
            return
        try:
            path = Path(self.abs_path(rel)).resolve()
            if path.parent == folder.resolve() and path.is_file():
                path.unlink()
        except OSError:
            pass
