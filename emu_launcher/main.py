"""EMUHUB – nativer Qt6-Game-Launcher für Switch-/3DS-Emulatoren deiner Wahl.

Start ohne Konsolenfenster:  main.pyw doppelklicken (oder: pyw main.pyw)
Start mit Konsole (Fehlersuche):  py main.py
"""
import ctypes
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

import music
import sfx
from data_manager import DataManager, get_base_dir
from i18n import DEFAULT_LANGUAGE, set_language
from main_window import MainWindow
from styles import apply_theme, set_custom_themes

APP_NAME = "EMUHUB"


def hide_own_console() -> None:
    """Windows: Gehört die Konsole nur uns (Doppelklick auf main.py), wird sie versteckt.
    Aus einem Terminal heraus hängen mehr Prozesse an der Konsole – die bleibt dann unangetastet.
    Sauberer ist der Start über main.pyw, dort entsteht gar keine Konsole."""
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        hwnd = kernel32.GetConsoleWindow()
        if hwnd and kernel32.GetConsoleProcessList((ctypes.c_uint * 4)(), 4) <= 2:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    except Exception:
        pass


def install_error_log(base: Path) -> None:
    """Ohne Konsole sieht man Fehler nicht – deshalb landen sie in emuhub_error.log."""
    log = base / "emuhub_error.log"
    previous = sys.excepthook

    def hook(exc_type, exc, tb):
        try:
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.now():%Y-%m-%d %H:%M:%S} ---\n")
                f.write("".join(traceback.format_exception(exc_type, exc, tb)))
        except OSError:
            pass
        previous(exc_type, exc, tb)

    sys.excepthook = hook


def load_app_icon(base: Path) -> QIcon | None:
    """assets/icon.ico bzw. assets/icon.png (falls vorhanden) als Fenster-/Taskleisten-Symbol."""
    for name in ("icon.ico", "icon.png"):
        path = base / "assets" / name
        if path.is_file():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
    return None


def main() -> int:
    base = get_base_dir()
    hide_own_console()
    install_error_log(base)
    if os.name == "nt":
        try:  # eigenes Taskleisten-Symbol statt dem von python.exe
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("EMUHUB.Launcher")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    icon = load_app_icon(base)
    if icon is not None:
        app.setWindowIcon(icon)

    data = DataManager(base)
    set_language(data.settings.get("language", DEFAULT_LANGUAGE))
    data.settings["custom_themes"] = set_custom_themes(data.settings.get("custom_themes"))   # eigene Themes zuerst
    apply_theme(app, data.settings.get("theme", ""))
    try:
        sfx.install(data.settings)
    except Exception:
        traceback.print_exc()
    try:   # Hintergrundmusik: ein Fehler hier darf den Start nie verhindern
        music.apply_settings(data.settings)
        app.aboutToQuit.connect(music.player().stop)
    except Exception:
        traceback.print_exc()
    window = MainWindow(data)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
