"""Emulator-Einrichtung als Seite der Einstellungen: Liste links, Details rechts.

Ändert nichts an den Konfigurationsdateien der Emulatoren – Grafik, Controller, Firmware und
Schlüssel stellt man im Emulator selbst ein. EMUHUB verwaltet Programmpfad, Standard-Argumente
und öffnet Emulator sowie Ordner.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from colorpicker import ColorDialog, ColorPicker
from data_manager import EMULATORS, MAX_EMULATOR_NAME, exe_filter
from emulators import ExeSearchWorker, exe_status, find_data_dir
from i18n import tr
from widgets import ask_yes_no, open_in_file_manager

STATUS_COLORS = {"ok": "#22c55e", "missing": "#f59e0b", "none": "#8b93a7"}
STATUS_ICONS = {"ok": "✓", "missing": "⚠", "none": "✗"}


def _row(*widgets: QWidget) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    for i, child in enumerate(widgets):
        h.addWidget(child, 1 if i == 0 else 0)
        if isinstance(child, QPushButton):
            child.setCursor(Qt.CursorShape.PointingHandCursor)
            child.setAutoDefault(False)
    return w


PRESET_COLORS = ("#ef4444", "#ec4899", "#14b8a6", "#eab308", "#06b6d4",
                 "#8b5cf6", "#84cc16", "#f43f5e", "#0ea5e9", "#94a3b8")


class AddEmulatorDialog(QDialog):
    """Name, Farbe und (optional) Programm eines neuen Emulators. `result_values` = (Name, Farbe, Pfad)."""

    def __init__(self, data_manager, taken_names: set[str], parent: QWidget | None = None):
        super().__init__(parent)
        self.data = data_manager
        self._taken = taken_names                 # kleingeschriebene, bereits vergebene Namen
        self.result_values: tuple[str, str, str] = ("", "", "")
        self._color = PRESET_COLORS[0]
        self.setWindowTitle(tr("Emulator hinzufügen"))
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(12)
        title = QLabel(tr("＋  Neuer Emulator"))
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(MAX_EMULATOR_NAME)
        self.name_edit.setPlaceholderText(tr("z. B. Yuzu, Lime3DS, Dolphin …"))
        form.addRow(tr("Name"), self.name_edit)

        self.swatches: list[QPushButton] = []
        swatch_row = QWidget()
        sh = QHBoxLayout(swatch_row)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.setSpacing(6)
        for color in PRESET_COLORS:
            b = QPushButton()
            b.setFixedSize(26, 26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setAutoDefault(False)
            b.setProperty("swatch", color)
            b.clicked.connect(lambda _=False, c=color: self._set_color(c))
            sh.addWidget(b)
            self.swatches.append(b)
        sh.addStretch(1)
        form.addRow(tr("Farbe"), swatch_row)
        self.picker = ColorPicker(self._color, title=False)
        self.picker.setMinimumHeight(230)
        form.addRow(tr("Farbwähler"), self.picker)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(tr("Pfad zur Emulator-.exe (kann später gesetzt werden)"))
        btn_browse = QPushButton(tr("Durchsuchen…"))
        form.addRow(tr("Programm (.exe)"), _row(self.path_edit, btn_browse))
        root.addLayout(form)

        self.error = QLabel()
        self.error.setStyleSheet("color: #f87171; font-weight: 600;")
        self.error.setWordWrap(True)
        self.error.hide()
        root.addWidget(self.error)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText(tr("Hinzufügen"))
        ok.setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        btn_browse.clicked.connect(self._browse)
        self.picker.colorChanged.connect(self._color_picked)
        self._set_color(self._color)

    def _set_color(self, color: str) -> None:
        self._color = QColor(color).name()
        if self.picker.hex() != self._color:
            self.picker.setColor(self._color, emit=False)
        self._paint()

    def _color_picked(self, color: QColor) -> None:
        self._color = color.name()
        self._paint()

    def _paint(self) -> None:
        for b in self.swatches:
            sel = b.property("swatch").lower() == self._color.lower()
            b.setStyleSheet(f"background-color: {b.property('swatch')}; border-radius: 13px; "
                            f"border: {'3px solid #ffffff' if sel else '1px solid rgba(0,0,0,90)'};")

    def _browse(self) -> None:
        start = os.path.dirname(self.path_edit.text().strip()) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, tr("Emulator auswählen"), start, exe_filter())
        if path:
            self.path_edit.setText(os.path.normpath(path))
            if not self.name_edit.text().strip():   # Namensvorschlag aus dem Dateinamen
                self.name_edit.setText(Path(path).stem.replace("_", " ")[:MAX_EMULATOR_NAME].strip().title())

    def _accept(self) -> None:
        name = self.name_edit.text().strip()
        problem = None
        if not name:
            problem = tr("Bitte einen Namen eingeben.")
        elif name.lower() in self._taken:
            problem = tr("Einen Emulator mit diesem Namen gibt es schon.")
        if problem:
            self.error.setText(problem)
            self.error.show()
            return
        self.result_values = (name, self._color, self.path_edit.text().strip().strip('"'))
        self.accept()


class EmulatorSetupPanel(QWidget):
    def __init__(self, data_manager, parent: QWidget | None = None):
        super().__init__(parent)
        self.data = data_manager
        self.path_edits: dict[str, QLineEdit] = {}
        self.args_edits: dict[str, QLineEdit] = {}
        self.apply_boxes: dict[str, QCheckBox] = {}
        self._pages: dict[str, dict] = {}
        self._items: dict[str, QListWidgetItem] = {}
        self._data_dirs: dict[str, object] = {}   # Name -> vorhandener Datenordner (oder None)

        self._colors: dict[str, str] = {}
        self._custom: set[str] = set(self.data.custom_emulators)   # eigene Emulatoren, die gerade angezeigt werden
        self._added: dict[str, str] = {}                           # neu (noch nicht gespeichert): Name -> Farbe
        self._removed: set[str] = set()                            # zum Entfernen vorgemerkt
        self._recolored: dict[str, str] = {}                       # geänderte Farben (noch nicht gespeichert)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        self.list = QListWidget()
        self.list.setObjectName("EmuList")
        self.stack = QStackedWidget()
        self.empty_label = QLabel(tr("Noch keine Emulatoren.\nKlicke links auf „＋ Emulator hinzufügen“."))
        self.empty_label.setObjectName("HintLabel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_add = QPushButton(tr("＋  Emulator hinzufügen"))
        self.btn_remove = QPushButton(tr("Entfernen"))
        self.btn_color = QPushButton(tr("🎨  Farbe ändern…"))
        left = QVBoxLayout()
        left.setSpacing(8)
        left.addWidget(self.list, 1)
        left.addWidget(self.btn_add)
        left.addWidget(self.btn_color)
        left.addWidget(self.btn_remove)
        side = QWidget()
        side.setFixedWidth(190)
        side.setLayout(left)
        left.setContentsMargins(0, 0, 0, 0)
        for b in (self.btn_add, self.btn_remove, self.btn_color):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setAutoDefault(False)
        for name, color in EMULATORS.items():
            self._add_page(name, color)
        root.addWidget(side)
        root.addWidget(self.stack, 1)
        root.addWidget(self.empty_label, 1)
        self.list.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.list.currentRowChanged.connect(lambda _=0: self._update_remove_button())
        self.btn_add.clicked.connect(self._add_emulator)
        self.btn_remove.clicked.connect(self._remove_emulator)
        self.btn_color.clicked.connect(self._change_color)
        self.list.setCurrentRow(0)
        self._update_remove_button()
        self._update_empty()

    def _add_page(self, name: str, color: str, path: str = "") -> None:
        item = QListWidgetItem(name)
        item.setForeground(QColor(color))
        self.list.addItem(item)
        self._items[name] = item
        self._colors[name] = color
        self.stack.addWidget(self._build_page(name, color))
        if path:
            self.path_edits[name].setText(path)
        self._refresh(name)

    # ---------------------------------------------- eigene Emulatoren verwalten
    def _current_name(self) -> str | None:
        item = self.list.currentItem()
        return next((n for n, it in self._items.items() if it is item), None)

    def _update_empty(self) -> None:
        empty = self.list.count() == 0
        self.stack.setVisible(not empty)
        self.empty_label.setVisible(empty)

    def _update_remove_button(self) -> None:
        name = self._current_name()
        self.btn_color.setEnabled(name is not None)
        self.btn_remove.setEnabled(name in self._custom)
        self.btn_remove.setToolTip("" if name in self._custom else tr("Eingebaute Emulatoren kann man nicht entfernen."))

    def _change_color(self) -> None:
        name = self._current_name()
        if name is None:
            return
        dlg = ColorDialog(self._colors[name], tr("Farbe für {name}", name=name), self)
        if not dlg.exec():
            return
        color = dlg.chosen()
        self._colors[name] = color
        self._items[name].setForeground(QColor(color))
        self._pages[name]["title"].setStyleSheet(f"color: {color}; font-size: 15pt; font-weight: 800;")
        if name in self._added:
            self._added[name] = color
        else:
            self._recolored[name] = color

    def color_changes(self) -> dict[str, str]:
        """Geänderte Farben bestehender Emulatoren: Name -> Farbe (neue Emulatoren tragen ihre Farbe in custom_changes)."""
        return dict(self._recolored)

    def _taken_names(self) -> set[str]:
        return {n.lower() for n in self._items} | {n.lower() for n in EMULATORS}

    def _add_emulator(self) -> None:
        dlg = AddEmulatorDialog(self.data, self._taken_names(), self)
        if not dlg.exec():
            return
        name, color, path = dlg.result_values
        self._custom.add(name)
        self._added[name] = color
        self._removed.discard(name)
        self._add_page(name, color, path)
        self.list.setCurrentRow(self.list.count() - 1)
        self._update_empty()

    def _remove_emulator(self) -> None:
        name = self._current_name()
        if name not in self._custom:
            return
        count = sum(1 for g in self.data.games if g.get("emulator") == name)
        if count:
            QMessageBox.information(
                self, tr("Emulator entfernen"),
                tr("„{name}“ wird noch von {count} Spiel(en) benutzt.\n\nÄndere oder entferne zuerst diese Spiele.",
                   name=name, count=count))
            return
        if not ask_yes_no(self, tr("Emulator entfernen"),
                          tr("„{name}“ aus der Liste entfernen?\n\nDas Programm selbst bleibt auf der Festplatte. "
                             "Wirksam nach „Speichern“.", name=name), default_yes=False):
            return
        row = self.list.row(self._items[name])
        page = self.stack.widget(row)
        self.stack.removeWidget(page)
        page.deleteLater()
        self.list.takeItem(row)
        for table in (self._items, self.path_edits, self.args_edits, self.apply_boxes, self._pages,
                      self._data_dirs, self._colors, self._recolored):
            table.pop(name, None)
        self._custom.discard(name)
        if name in self._added:
            del self._added[name]       # nie gespeichert -> nichts zu entfernen
        else:
            self._removed.add(name)
        self._update_remove_button()
        self._update_empty()

    def custom_changes(self) -> tuple[dict[str, str], set[str]]:
        """(neu hinzugefügte Emulatoren: Name -> Farbe, zum Entfernen vorgemerkte Namen)."""
        return dict(self._added), set(self._removed)

    # ------------------------------------------------------------------ Seiten
    def _build_page(self, name: str, color: str) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(10)

        title = QLabel(name)
        title.setStyleSheet(f"color: {color}; font-size: 15pt; font-weight: 800;")
        status = QLabel()
        status.setWordWrap(True)
        games = QLabel()
        games.setObjectName("HintLabel")
        v.addWidget(title)
        v.addWidget(status)
        v.addWidget(games)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        path_edit = QLineEdit(self.data.emulators.get(name, ""))
        path_edit.setPlaceholderText(tr("Pfad zur Emulator-.exe"))
        btn_browse = QPushButton(tr("Durchsuchen…"))
        btn_find = QPushButton(tr("🔍  Automatisch suchen"))
        form.addRow(tr("Programm (.exe)"), _row(path_edit, btn_browse, btn_find))
        args_edit = QLineEdit(self.data.emulator_args.get(name, ""))
        args_edit.setPlaceholderText(tr("Optional – siehe Dokumentation des Emulators"))
        form.addRow(tr("Standard-Argumente"), args_edit)
        v.addLayout(form)
        hint = QLabel(tr("Gilt für alle Spiele dieses Emulators, bei denen „Start-Argumente“ leer ist. "
                         "{rom} = Position des ROM-Pfads."))
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        v.addWidget(hint)

        btn_open = QPushButton(tr("▶  Emulator öffnen (einrichten)"))
        btn_open.setObjectName("PrimaryButton")
        btn_open.setToolTip(tr("Öffnet den Emulator ohne Spiel – Grafik, Controller, Firmware und "
                               "Schlüssel stellst du dort selbst ein."))
        btn_prog = QPushButton(tr("📂  Programmordner"))
        btn_data = QPushButton(tr("📂  Datenordner"))
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        for b in (btn_open, btn_prog, btn_data):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setAutoDefault(False)
            buttons.addWidget(b)
        buttons.addStretch(1)
        v.addLayout(buttons)
        data_info = QLabel()
        data_info.setObjectName("HintLabel")
        data_info.setWordWrap(True)
        v.addWidget(data_info)

        apply_box = QCheckBox(tr("Diesen Pfad in allen Spielen dieses Emulators übernehmen"))
        apply_box.setToolTip(tr("Entfernt die eigenen Pfade der Spiele; wirkt erst beim Speichern."))
        v.addWidget(apply_box)
        v.addStretch(1)

        self.path_edits[name], self.args_edits[name], self.apply_boxes[name] = path_edit, args_edit, apply_box
        self._pages[name] = {"title": title, "status": status, "games": games, "data_info": data_info, "btn_open": btn_open,
                             "btn_prog": btn_prog, "btn_data": btn_data, "btn_find": btn_find}
        path_edit.textChanged.connect(lambda _=None, n=name: self._refresh(n))
        btn_browse.clicked.connect(lambda _=False, n=name: self._browse(n))
        btn_find.clicked.connect(lambda _=False, n=name: self._start_search(n))
        btn_open.clicked.connect(lambda _=False, n=name: self._open_emulator(n))
        btn_prog.clicked.connect(lambda _=False, n=name: self._open_program_dir(n))
        btn_data.clicked.connect(lambda _=False, n=name: self._open_data_dir(n))
        return page

    # ------------------------------------------------------------------ Status
    def current_path(self, name: str) -> str:
        return self.path_edits[name].text().strip().strip('"')

    def _refresh(self, name: str) -> None:
        page, path = self._pages[name], self.current_path(name)
        state = exe_status(path)
        self._items[name].setText(f"{STATUS_ICONS[state]}  {name}")
        text = {"none": tr("✗  Noch kein Programm festgelegt."),
                "missing": tr("⚠  Datei nicht gefunden:\n{path}", path=path),
                "ok": tr("✓  Bereit: {path}", path=path)}[state]
        page["status"].setText(text)
        page["status"].setStyleSheet(f"color: {STATUS_COLORS[state]}; font-weight: 600;")
        page["btn_open"].setEnabled(state == "ok")
        page["btn_prog"].setEnabled(state == "ok")
        box = self.apply_boxes[name]   # nur mit funktionierendem Standardpfad sinnvoll
        box.setEnabled(state == "ok")
        if state != "ok":
            box.setChecked(False)
        count = sum(1 for g in self.data.games if g.get("emulator") == name)
        page["games"].setText(tr("Genutzt von {count} Spiel(en)", count=count))

        found, tried = find_data_dir(name, path)
        if found:
            kind = tr("portabel") if found[1] == "portable" else "AppData"
            page["data_info"].setText(tr("Datenordner: {path}  ({kind})", path=found[0], kind=kind))
        else:
            checked = "\n".join(f"• {p}" for p in tried) or tr("• (kein Emulator-Pfad hinterlegt)")
            page["data_info"].setText(tr(
                "Datenordner nicht gefunden – er entsteht meist beim ersten Start des Emulators.\n"
                "Geprüft:\n{paths}", paths=checked))
        page["btn_data"].setEnabled(found is not None)
        page["btn_data"].setToolTip(str(found[0]) if found else "")
        self._data_dirs[name] = found[0] if found else None

    # ------------------------------------------------------------------ Aktionen
    def _browse(self, name: str) -> None:
        start = os.path.dirname(self.current_path(name)) or os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(self, tr("{name} auswählen", name=name), start, exe_filter())
        if path:
            self.path_edits[name].setText(os.path.normpath(path))

    def _start_search(self, name: str, roots=None) -> None:
        btn = self._pages[name]["btn_find"]
        btn.setEnabled(False)
        btn.setText(tr("⏳  Suche läuft …"))
        worker = ExeSearchWorker(name, roots)
        worker.found.connect(self._on_found)
        worker.start()

    def _on_found(self, name: str, paths: list) -> None:
        btn = self._pages[name]["btn_find"]
        btn.setEnabled(True)
        btn.setText(tr("🔍  Automatisch suchen"))
        if not self.window().isVisible():   # Einstellungen wurden geschlossen (Tabwechsel zählt nicht)
            return
        if not paths:
            if ask_yes_no(self, tr("Nichts gefunden"),
                          tr("Für {name} wurde kein Programm gefunden.\n\nIn einem Ordner deiner Wahl suchen?",
                             name=name)):
                folder = QFileDialog.getExistingDirectory(self, tr("Ordner zum Durchsuchen wählen"))
                if folder:
                    self._start_search(name, [Path(folder)])
            return
        chosen = paths[0]
        if len(paths) > 1:
            chosen, accepted = QInputDialog.getItem(
                self, tr("Programm auswählen"),
                tr("Mehrere Treffer – welches Programm gehört zu {name}?", name=name), paths, 0, False)
            if not accepted:
                return
        self.path_edits[name].setText(os.path.normpath(chosen))

    def _open_emulator(self, name: str) -> None:
        exe = self.current_path(name)
        if not os.path.isfile(exe):
            QMessageBox.warning(self, tr("Emulator nicht gefunden"),
                                tr("Das Programm existiert nicht:\n{path}", path=exe or tr("(leer)")))
            return
        try:
            subprocess.Popen([exe], cwd=os.path.dirname(exe) or None)   # ohne Spiel: Oberfläche des Emulators
        except OSError as exc:
            QMessageBox.critical(self, tr("Start fehlgeschlagen"),
                                 tr("{emu} konnte nicht gestartet werden:\n{exc}", emu=name, exc=exc))

    def _open_program_dir(self, name: str) -> None:
        exe = self.current_path(name)
        if os.path.isfile(exe):
            open_in_file_manager(os.path.dirname(exe), self)

    def _open_data_dir(self, name: str) -> None:
        folder = self._data_dirs.get(name)
        if folder is not None:
            open_in_file_manager(str(folder), self)

    # ------------------------------------------------------------------ Ergebnis
    def values(self) -> tuple[dict[str, str], dict[str, str], set[str]]:
        """(Pfade, Standard-Argumente, Emulatoren, deren Pfad in allen Spielen übernommen werden soll)."""
        paths = {n: self.current_path(n) for n in self.path_edits}
        args = {n: e.text().strip() for n, e in self.args_edits.items()}
        apply_to = {n for n, b in self.apply_boxes.items() if b.isEnabled() and b.isChecked()}
        return paths, args, apply_to
