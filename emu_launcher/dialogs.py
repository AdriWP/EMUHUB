"""Dialoge: Spiel hinzufügen/bearbeiten und Einstellungen."""
from __future__ import annotations

import os

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSlider, QTabWidget,
    QVBoxLayout, QWidget,
)

import music
import sfx
import styles
from data_manager import (
    COVER_SHAPES, EMULATORS, N3DS_EXT, cover_aspect, exe_filter, guess_emulator_for_rom, image_filter,
    rom_filter, same_path, split_args,
)
from styles import BUILTIN_THEMES, DEFAULT_THEME, clean_custom_themes, set_custom_themes
from theme_editor import ThemeEditorDialog
from emulator_setup import EmulatorSetupPanel
from i18n import LANGUAGES, get_language, tr
from widgets import ask_yes_no, make_cover_pixmap, open_in_file_manager


def styles_custom_copy(raw) -> dict[str, dict[str, str]]:
    """Arbeitskopie der eigenen Themes (bereinigt), damit Abbrechen nichts verändert."""
    return clean_custom_themes(raw)


def _path_row(edit: QLineEdit, *buttons: QPushButton) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    h.addWidget(edit, 1)
    for b in buttons:
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        h.addWidget(b)
    return w


def _start_dir(path: str) -> str:
    if path:
        d = path if os.path.isdir(path) else os.path.dirname(path)
        if os.path.isdir(d):
            return d
    return os.path.expanduser("~")


class GameDialog(QDialog):
    PREVIEW_MAX_W = 260
    PREVIEW_H = 220

    def __init__(self, data_manager, game: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.data = data_manager
        self.game = game
        self.result_data: dict | None = None

        # Cover-Zustand
        self._cover_rel = game["cover"] if game else ""   # bestehendes Cover
        self._cover_src = ""                               # neu gewählte Datei
        self._prev_emu = game["emulator"] if game else ""

        self.setWindowTitle(tr("Spiel bearbeiten") if game else tr("Spiel hinzufügen"))
        self.setMinimumWidth(780)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 18)
        root.setSpacing(16)

        head = QLabel(self.windowTitle())
        head.setObjectName("DialogTitle")
        root.addWidget(head)

        body = QHBoxLayout()
        body.setSpacing(22)
        root.addLayout(body, 1)

        # ---- linke Spalte: Cover
        left = QVBoxLayout()
        left.setSpacing(8)
        self.preview = QLabel()
        self.preview.setObjectName("CoverPreview")
        self.preview.setFixedSize(165, self.PREVIEW_H)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.preview)
        btn_cover = QPushButton(tr("Cover wählen…"))
        btn_cover_clear = QPushButton(tr("Cover entfernen"))
        for b in (btn_cover, btn_cover_clear):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            left.addWidget(b)
        hint = QLabel(tr("PNG/JPG – wird automatisch\nnach covers/ kopiert und\nauf Kachelgröße skaliert."))
        hint.setObjectName("HintLabel")
        left.addWidget(hint)
        left.addStretch(1)
        body.addLayout(left)

        # ---- rechte Spalte: Formular
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        body.addLayout(form, 1)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("z. B. The Legend of Zelda: Tears of the Kingdom"))
        form.addRow(tr("Spielname"), self.name_edit)

        self.rom_edit = QLineEdit()
        self.rom_edit.setPlaceholderText(tr("Pfad zur .nsp / .xci / .3ds / .cia …"))
        btn_rom = QPushButton(tr("Durchsuchen…"))
        form.addRow(tr("ROM-Datei"), _path_row(self.rom_edit, btn_rom))

        self.emu_combo = QComboBox()
        self.emu_combo.addItems(list(EMULATORS.keys()))
        form.addRow("Emulator", self.emu_combo)

        self.shape_combo = QComboBox()
        for key, label in COVER_SHAPES.items():
            self.shape_combo.addItem(tr(label), key)
        self.shape_combo.setToolTip(tr("Form der Spielekachel in der Bibliothek"))
        form.addRow(tr("Kachelformat"), self.shape_combo)

        self.emu_path_edit = QLineEdit()
        self.emu_path_edit.setPlaceholderText(tr("Pfad zur Emulator-.exe"))
        btn_emu = QPushButton(tr("Durchsuchen…"))
        emu_box = QWidget()
        emu_v = QVBoxLayout(emu_box)
        emu_v.setContentsMargins(0, 0, 0, 0)
        emu_v.setSpacing(3)
        emu_v.addWidget(_path_row(self.emu_path_edit, btn_emu))
        emu_hint = QLabel(tr("Vorbelegt mit dem Standardpfad (Einstellungen → Emulatoren). Nur ändern, wenn dieses Spiel einen anderen Emulator-Ordner braucht."))
        emu_hint.setObjectName("HintLabel")
        emu_v.addWidget(emu_hint)
        form.addRow(tr("Emulator-Pfad"), emu_box)

        self.args_edit = QLineEdit()
        self.args_edit.setPlaceholderText(tr("z. B. -f   ·   {rom} = Position des ROM-Pfads"))
        args_box = QWidget()
        args_v = QVBoxLayout(args_box)
        args_v.setContentsMargins(0, 0, 0, 0)
        args_v.setSpacing(3)
        args_v.addWidget(self.args_edit)
        args_hint = QLabel(tr("Ohne {rom} wird der ROM-Pfad automatisch ans Ende gehängt."))
        args_hint.setObjectName("HintLabel")
        args_v.addWidget(args_hint)
        form.addRow(tr("Start-Argumente"), args_box)

        self.mod_edit = QLineEdit()
        self.mod_edit.setPlaceholderText(tr("Optional: Mod-Ordner des Spiels"))
        btn_mod = QPushButton(tr("Wählen…"))
        btn_mod_open = QPushButton(tr("Öffnen"))
        form.addRow(tr("Mod-Ordner"), _path_row(self.mod_edit, btn_mod, btn_mod_open))

        self.shot_edit = QLineEdit()
        self.shot_edit.setPlaceholderText(tr("Optional: eigener Screenshot-Ordner (leer = automatisch)"))
        btn_shot = QPushButton(tr("Wählen…"))
        btn_shot_open = QPushButton(tr("Öffnen"))
        form.addRow(tr("Screenshot-Ordner"), _path_row(self.shot_edit, btn_shot, btn_shot_open))

        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText(
            tr("Aktive Mods, Grafik-Settings, Performance-Notizen …\n"
            "z. B.\n• 60 FPS Mod aktiv\n• Auflösung 2x, Vulkan\n• Shader-Cache vorkompiliert"))
        self.notes_edit.setMinimumHeight(150)
        form.addRow(tr("Notizen && Mods"), self.notes_edit)  # && = literales "&"

        # ---- Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_btn.setText(tr("Speichern"))
        save_btn.setObjectName("PrimaryButton")
        save_btn.setDefault(True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        root.addWidget(buttons)

        # ---- Signale
        btn_cover.clicked.connect(self._choose_cover)
        btn_cover_clear.clicked.connect(self._clear_cover)
        btn_rom.clicked.connect(self._choose_rom)
        btn_emu.clicked.connect(self._choose_emulator)
        btn_mod.clicked.connect(self._choose_mod_dir)
        btn_mod_open.clicked.connect(lambda: open_in_file_manager(self.mod_edit.text().strip(), self))
        btn_shot.clicked.connect(self._choose_shot_dir)
        btn_shot_open.clicked.connect(lambda: open_in_file_manager(self.shot_edit.text().strip(), self))
        self.emu_combo.currentTextChanged.connect(self._emulator_changed)
        self.name_edit.textChanged.connect(lambda _: self._update_preview())
        self.rom_edit.textChanged.connect(lambda _: self._update_preview())
        self.shape_combo.currentIndexChanged.connect(lambda _: self._update_preview())
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        # ---- Werte füllen
        if game:
            self.name_edit.setText(game["name"])
            self.rom_edit.setText(game["rom_path"])
            self.emu_combo.setCurrentText(game["emulator"])
            self.emu_path_edit.setText(self.data.resolve_emulator_path(game))
            self.args_edit.setText(game["args"])
            self.mod_edit.setText(game["mod_path"])
            self.shot_edit.setText(game.get("screenshot_dir", ""))
            idx = self.shape_combo.findData(game.get("cover_shape", "auto"))
            self.shape_combo.setCurrentIndex(max(idx, 0))
            self.notes_edit.setPlainText(game["notes"])
        else:
            self.emu_combo.setCurrentText(self._prev_emu)
            self.emu_path_edit.setText(self.data.emulators.get(self._prev_emu, ""))
        self._update_preview()

    # ---------------------------------------------------------------- Cover
    def _current_cover_path(self) -> str:
        if self._cover_src:
            return self._cover_src
        return self.data.abs_path(self._cover_rel) if self._cover_rel else ""

    def _aspect(self) -> float:
        return cover_aspect({
            "cover_shape": self.shape_combo.currentData(),
            "emulator": self.emu_combo.currentText(),
            "rom_path": self.rom_edit.text().strip(),
        }, self._current_cover_path())

    def _update_preview(self) -> None:
        # Vorschau zeigt die Kachel genau so wie in der Bibliothek: gleiche Höhe,
        # Breite passend zum Bildformat.
        h = self.PREVIEW_H
        w = min(self.PREVIEW_MAX_W, int(round(h * self._aspect())))
        self.preview.setFixedSize(w, h)
        self.preview.setPixmap(make_cover_pixmap(
            self._current_cover_path(), w, h,
            self.emu_combo.currentText(), self.name_edit.text() or "?"))

    def _choose_cover(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Cover auswählen"), _start_dir(self._cover_src), image_filter())
        if path:
            self._cover_src = path
            self._update_preview()

    def _clear_cover(self) -> None:
        self._cover_src = ""
        self._cover_rel = ""
        self._update_preview()

    # ---------------------------------------------------------------- Pfade
    def _choose_rom(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("ROM auswählen"), _start_dir(self.rom_edit.text()), rom_filter())
        if not path:
            return
        self.rom_edit.setText(os.path.normpath(path))
        if not self.name_edit.text().strip():
            self.name_edit.setText(os.path.splitext(os.path.basename(path))[0])
        guess = guess_emulator_for_rom(path)
        current = self.emu_combo.currentText()
        if guess and guess != current:   # 3DS-ROM -> 3DS-Emulator; Switch-ROM nur, wenn gerade der 3DS-Emulator steht
            if os.path.splitext(path)[1].lower() in N3DS_EXT or current.lower() == "citra":
                self.emu_combo.setCurrentText(guess)

    def _choose_emulator(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("{name} auswählen", name=self.emu_combo.currentText()),
            _start_dir(self.emu_path_edit.text()), exe_filter())
        if path:
            self.emu_path_edit.setText(os.path.normpath(path))

    def _choose_mod_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, tr("Mod-Ordner auswählen"), _start_dir(self.mod_edit.text()))
        if path:
            self.mod_edit.setText(os.path.normpath(path))

    def _choose_shot_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, tr("Screenshot-Ordner auswählen"), _start_dir(self.shot_edit.text()))
        if path:
            self.shot_edit.setText(os.path.normpath(path))

    def _emulator_changed(self, new_emu: str) -> None:
        """Beim Wechsel des Emulators den gemerkten Standardpfad übernehmen,
        sofern der Nutzer keinen eigenen Pfad eingetragen hat."""
        current = self.emu_path_edit.text().strip()
        if not current or current == self.data.emulators.get(self._prev_emu, ""):
            self.emu_path_edit.setText(self.data.emulators.get(new_emu, ""))
        self._prev_emu = new_emu
        self._update_args_placeholder()
        self._update_preview()

    def _update_args_placeholder(self) -> None:
        """Zeigt die Standard-Argumente des Emulators, solange das Feld leer ist."""
        default = self.data.emulator_args.get(self.emu_combo.currentText(), "").strip()
        self.args_edit.setPlaceholderText(
            tr("Standard: {args}", args=default) if default
            else tr("z. B. -f   ·   {rom} = Position des ROM-Pfads"))

    # ------------------------------------------------------------- Speichern
    def _on_accept(self) -> None:
        name = self.name_edit.text().strip()
        rom = self.rom_edit.text().strip().strip('"')
        emu_path = self.emu_path_edit.text().strip().strip('"')
        args = self.args_edit.text().strip()
        mod = self.mod_edit.text().strip().strip('"')
        shot = self.shot_edit.text().strip().strip('"')

        if not name:
            QMessageBox.warning(self, tr("Fehlende Angabe"), tr("Bitte einen Spielnamen eingeben."))
            self.name_edit.setFocus()
            return
        if not rom:
            QMessageBox.warning(self, tr("Fehlende Angabe"), tr("Bitte eine ROM-Datei auswählen."))
            self.rom_edit.setFocus()
            return
        try:
            split_args(args)
        except ValueError as exc:
            QMessageBox.warning(self, tr("Ungültige Start-Argumente"),
                                tr("Die Argumente konnten nicht gelesen werden:\n{exc}\n\n"
                                   "Bitte Anführungszeichen prüfen.", exc=exc))
            self.args_edit.setFocus()
            return

        problems = []
        if not os.path.isfile(rom):
            problems.append(tr("• Die ROM-Datei wurde nicht gefunden."))
        if emu_path and not os.path.isfile(emu_path):
            problems.append(tr("• Die Emulator-Datei wurde nicht gefunden."))
        if mod and not os.path.isdir(mod):
            problems.append(tr("• Der Mod-Ordner wurde nicht gefunden."))
        if shot and not os.path.isdir(shot):
            problems.append(tr("• Der Screenshot-Ordner wurde nicht gefunden."))
        if problems:
            if not ask_yes_no(self, tr("Pfade prüfen"),
                              tr("{problems}\n\nTrotzdem speichern?", problems="\n".join(problems))):
                return

        cover_rel = self._cover_rel
        if self._cover_src:
            try:
                cover_rel = self.data.import_cover(self._cover_src)
            except ValueError as exc:
                QMessageBox.warning(self, tr("Cover-Fehler"), str(exc))
                return

        self.result_data = {
            "name": name,
            "cover": cover_rel,
            "rom_path": rom,
            "emulator": self.emu_combo.currentText(),
            "emulator_path": "" if same_path(emu_path, self.data.emulators.get(self.emu_combo.currentText(), "")) else emu_path,
            "args": args,
            "notes": self.notes_edit.toPlainText().rstrip(),
            "mod_path": mod,
            "screenshot_dir": shot,
            "cover_shape": self.shape_combo.currentData(),
        }
        self.accept()


class SettingsDialog(QDialog):
    """Einstellungen von EMUHUB: Allgemein, Design, Bibliothek und Emulator-Pfade."""

    BG_PREVIEW = (300, 169)

    def __init__(self, data_manager, parent: QWidget | None = None):
        super().__init__(parent)
        self.data = data_manager
        st = self.data.settings
        self._bg_rel = st.get("background", "")   # aktuell gespeichertes Bild
        self._bg_src = ""                          # neu gewählte Datei
        self.setWindowTitle(tr("Einstellungen"))
        self.setMinimumSize(860, 600)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 18)
        root.setSpacing(14)
        head = QLabel(tr("⚙  Einstellungen"))
        head.setObjectName("DialogTitle")
        root.addWidget(head)

        tabs = QTabWidget()
        tabs.setObjectName("SettingsTabs")
        root.addWidget(tabs, 1)

        # ----------------------------------------------------------- Allgemein
        general = QWidget()
        gform = QFormLayout(general)
        gform.setContentsMargins(18, 18, 18, 18)
        gform.setHorizontalSpacing(16)
        gform.setVerticalSpacing(14)
        self.lang_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.lang_combo.addItem(name, code)
        self.lang_combo.setCurrentIndex(max(0, self.lang_combo.findData(get_language())))
        gform.addRow("Sprache / Language", self.lang_combo)
        lang_hint = QLabel(tr("Wird sofort übernommen."))
        lang_hint.setObjectName("HintLabel")
        gform.addRow("", lang_hint)
        tabs.addTab(general, tr("🌐  Allgemein"))

        # ------------------------------------------------------------ Design
        design = QWidget()
        form = QFormLayout(design)
        form.setContentsMargins(18, 18, 18, 18)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)

        self._custom_themes = styles_custom_copy(st.get("custom_themes"))   # Arbeitskopie bis „Speichern“
        self.theme_combo = QComboBox()
        self._fill_theme_combo(st.get("theme", DEFAULT_THEME))
        btn_theme_new = QPushButton(tr("＋  Eigenes Theme…"))
        self.btn_theme_edit = QPushButton(tr("Bearbeiten…"))
        self.btn_theme_del = QPushButton(tr("Löschen"))
        theme_row = QWidget()
        th = QHBoxLayout(theme_row)
        th.setContentsMargins(0, 0, 0, 0)
        th.addWidget(self.theme_combo, 1)
        for b in (btn_theme_new, self.btn_theme_edit, self.btn_theme_del):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setAutoDefault(False)
            th.addWidget(b)
        form.addRow(tr("Farb-Theme"), theme_row)
        btn_theme_new.clicked.connect(self._theme_new)
        self.btn_theme_edit.clicked.connect(self._theme_edit)
        self.btn_theme_del.clicked.connect(self._theme_delete)
        self.theme_combo.currentTextChanged.connect(lambda _=None: self._update_theme_buttons())
        self._update_theme_buttons()

        bg_box = QWidget()
        bg_v = QVBoxLayout(bg_box)
        bg_v.setContentsMargins(0, 0, 0, 0)
        bg_v.setSpacing(8)
        self.bg_preview = QLabel()
        self.bg_preview.setObjectName("CoverPreview")
        self.bg_preview.setFixedSize(*self.BG_PREVIEW)
        self.bg_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bg_v.addWidget(self.bg_preview)
        bg_btns = QHBoxLayout()
        btn_bg = QPushButton(tr("Bild wählen…"))
        btn_bg_clear = QPushButton(tr("Entfernen"))
        for b in (btn_bg, btn_bg_clear):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            bg_btns.addWidget(b)
        bg_btns.addStretch(1)
        bg_v.addLayout(bg_btns)
        form.addRow(tr("Hintergrundbild"), bg_box)

        self.dim_slider, dim_row = self._slider_row(0, 90, int(st.get("background_dim", 55)), "%")
        form.addRow(tr("Abdunklung"), dim_row)
        dim_hint = QLabel(tr("Je stärker abgedunkelt, desto besser lesbar sind Kacheln und Texte."))
        dim_hint.setObjectName("HintLabel")
        form.addRow("", dim_hint)
        tabs.addTab(design, "🎨  Design")

        # -------------------------------------------------------- Bibliothek
        lib = QWidget()
        lform = QFormLayout(lib)
        lform.setContentsMargins(18, 18, 18, 18)
        lform.setHorizontalSpacing(16)
        lform.setVerticalSpacing(14)
        try:
            scale = int(round(float(st.get("tile_scale", 1.0)) * 100))
        except (TypeError, ValueError):
            scale = 100
        self.size_slider, size_row = self._slider_row(60, 160, scale, "%")
        lform.addRow(tr("Kachelgröße"), size_row)
        size_hint = QLabel(tr("Auch direkt in der Bibliothek: Regler oben rechts oder Strg + Mausrad."))
        size_hint.setObjectName("HintLabel")
        lform.addRow("", size_hint)
        self.fav_first = QCheckBox(tr("Favoriten immer oben anzeigen"))
        self.fav_first.setChecked(bool(st.get("favorites_first", True)))
        lform.addRow(tr("Sortierung"), self.fav_first)
        self.minimize = QCheckBox(tr("EMUHUB beim Spielstart minimieren"))
        self.minimize.setChecked(bool(st.get("minimize_on_launch", False)))
        lform.addRow(tr("Spielstart"), self.minimize)
        tabs.addTab(lib, tr("📚  Bibliothek"))

        # -------------------------------------------------------- Emulatoren
        self.emu_panel = EmulatorSetupPanel(self.data)
        tabs.addTab(self.emu_panel, tr("🎮  Emulatoren"))

        # ------------------------------------------------------------- Musik
        tabs.addTab(self._build_music_tab(), tr("🎵  Musik & Sound"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_btn.setText(tr("Speichern"))
        save_btn.setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        btn_bg.clicked.connect(self._choose_background)
        btn_bg_clear.clicked.connect(self._clear_background)
        self._update_bg_preview()

    # ----------------------------------------------------------- eigene Themes
    def _all_theme_names(self) -> list[str]:
        return list(BUILTIN_THEMES) + [n for n in self._custom_themes if n not in BUILTIN_THEMES]

    def _fill_theme_combo(self, select: str) -> None:
        self.theme_combo.blockSignals(True)
        self.theme_combo.clear()
        self.theme_combo.addItems(self._all_theme_names())
        names = self._all_theme_names()
        self.theme_combo.setCurrentText(select if select in names else DEFAULT_THEME)
        self.theme_combo.blockSignals(False)

    def _update_theme_buttons(self) -> None:
        custom = self.theme_combo.currentText() in self._custom_themes
        self.btn_theme_edit.setEnabled(custom)
        self.btn_theme_del.setEnabled(custom)

    def _theme_new(self) -> None:
        base = self._custom_themes.get(self.theme_combo.currentText()) or BUILTIN_THEMES.get(self.theme_combo.currentText())
        dlg = ThemeEditorDialog(set(self._all_theme_names()), base=base, parent=self)
        if dlg.exec():
            name, theme = dlg.result_values
            self._custom_themes[name] = theme
            self._fill_theme_combo(name)
            self._update_theme_buttons()

    def _theme_edit(self) -> None:
        old = self.theme_combo.currentText()
        if old not in self._custom_themes:
            return
        dlg = ThemeEditorDialog(set(self._all_theme_names()) - {old}, name=old, base=self._custom_themes[old], parent=self)
        if dlg.exec():
            name, theme = dlg.result_values
            del self._custom_themes[old]
            self._custom_themes[name] = theme
            self._fill_theme_combo(name)
            self._update_theme_buttons()

    def _theme_delete(self) -> None:
        name = self.theme_combo.currentText()
        if name in self._custom_themes and ask_yes_no(
                self, tr("Theme löschen"), tr("Eigenes Theme „{name}“ löschen?", name=name), default_yes=False):
            del self._custom_themes[name]
            self._fill_theme_combo(DEFAULT_THEME)
            self._update_theme_buttons()

    # ----------------------------------------------------------------- Musik
    def _build_music_tab(self) -> QWidget:
        """Musik-Einstellungen wirken SOFORT (ohne Speichern) – wie bei einem Mediaplayer."""
        st = self.data.settings
        self._music = music.player()
        self._save_timer = QTimer(self)             # Lautstärke: gesammelt speichern, nicht bei jedem Pixel
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.data.save)

        page = QWidget()
        form = QFormLayout(page)
        form.setContentsMargins(18, 18, 18, 18)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)

        self.music_on = QCheckBox(tr("Hintergrundmusik abspielen"))
        self.music_on.setChecked(bool(st.get("music_enabled", True)))
        form.addRow(tr("Musik"), self.music_on)

        self.music_edit = QLineEdit(st.get("music_file", ""))
        self.music_edit.setReadOnly(True)
        self.music_edit.setPlaceholderText(tr("Keine Datei ausgewählt"))
        btn_pick = QPushButton(tr("MP3 wählen…"))
        btn_none = QPushButton(tr("Entfernen"))
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(self.music_edit, 1)
        for b in (btn_pick, btn_none):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setAutoDefault(False)
            h.addWidget(b)
        form.addRow(tr("Musikdatei"), row)

        try:
            volume = int(st.get("music_volume", music.DEFAULT_VOLUME))
        except (TypeError, ValueError):
            volume = music.DEFAULT_VOLUME
        self.volume_slider, volume_row = self._slider_row(0, 100, volume, "%")
        form.addRow(tr("Lautstärke"), volume_row)

        try:
            sfx_volume = int(st.get("sfx_volume", sfx.DEFAULT_SFX_VOLUME))
        except (TypeError, ValueError):
            sfx_volume = sfx.DEFAULT_SFX_VOLUME
        self.sfx_slider, sfx_row = self._slider_row(0, 100, sfx_volume, "%")
        self.sfx_slider.setEnabled(sfx.effects().usable)
        form.addRow(tr("Soundeffekte"), sfx_row)
        sfx_hint = QLabel(tr("Blasen-Klang beim Darüberfahren mit Maus oder Controller. 0 % = aus. "
                             "Gilt sofort; der Regler spielt zur Probe den Klang ab."))
        sfx_hint.setObjectName("HintLabel")
        sfx_hint.setWordWrap(True)
        form.addRow("", sfx_hint)
        self._sfx_preview = QTimer(self)             # nach dem Verschieben einmal zur Probe abspielen
        self._sfx_preview.setSingleShot(True)
        self._sfx_preview.setInterval(220)
        self._sfx_preview.timeout.connect(lambda: sfx.effects().play_hover(force=True))
        self.sfx_slider.valueChanged.connect(self._sfx_changed)

        self.music_status = QLabel()
        self.music_status.setWordWrap(True)
        self.music_status.setObjectName("HintLabel")
        form.addRow("", self.music_status)
        hint = QLabel(tr("Die Musik läuft in Endlosschleife. Änderungen hier gelten sofort und werden "
                         "automatisch gespeichert – ein Klick auf „Speichern“ ist nicht nötig."))
        hint.setObjectName("HintLabel")
        hint.setWordWrap(True)
        form.addRow("", hint)

        enabled = self._music.usable
        for w in (self.music_on, btn_pick, btn_none, self.volume_slider):
            w.setEnabled(enabled)
        self.music_on.toggled.connect(self._music_toggled)
        btn_pick.clicked.connect(self._music_pick)
        btn_none.clicked.connect(self._music_clear)
        self.volume_slider.valueChanged.connect(self._music_volume)
        self._music.state_changed.connect(self._music_refresh)
        self._music_refresh()
        return page

    def _sfx_changed(self, value: int) -> None:
        self.data.settings["sfx_volume"] = int(value)
        sfx.effects().set_volume(value)
        self._sfx_preview.start()
        self._save_timer.start()

    def _music_toggled(self, on: bool) -> None:
        self.data.settings["music_enabled"] = bool(on)
        self._music.set_enabled(on)
        self._save_timer.start()

    def _music_pick(self) -> None:
        start = os.path.dirname(self.music_edit.text()) or _start_dir("")
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Musikdatei auswählen"), start,
            f"{tr('Musik')} ({music.AUDIO_EXTENSIONS});;{tr('Alle Dateien')} (*)")
        if not path:
            return
        path = os.path.normpath(path)
        self.music_edit.setText(path)
        self.data.settings["music_file"] = path
        self.data.settings["music_enabled"] = True
        self.music_on.blockSignals(True)
        self.music_on.setChecked(True)
        self.music_on.blockSignals(False)
        self._music.set_file(path, True)
        self._save_timer.start()

    def _music_clear(self) -> None:
        self.music_edit.setText("")
        self.data.settings["music_file"] = ""
        self._music.set_file("", self.music_on.isChecked())
        self._save_timer.start()

    def _music_volume(self, value: int) -> None:
        self.data.settings["music_volume"] = int(value)
        self._music.set_volume(value)   # sofort hörbar
        self._save_timer.start()

    def _music_refresh(self) -> None:
        m = self._music
        if not m.usable:
            text = tr("⚠  Musikwiedergabe nicht verfügbar (Qt Multimedia fehlt – „pip install PySide6“).")
        elif not m.path:
            text = tr("Keine Musikdatei ausgewählt.")
        elif not m.file_exists():
            text = tr("⚠  Datei nicht gefunden:\n{path}", path=m.path)
        elif m.error:
            text = tr("⚠  Datei kann nicht abgespielt werden:\n{error}", error=m.error)
        elif m.playing:
            text = tr("▶  Spielt: {name}", name=os.path.basename(m.path))
        else:
            text = tr("⏸  Pausiert: {name}", name=os.path.basename(m.path))
        self.music_status.setText(text)

    def done(self, result: int) -> None:
        if self._save_timer.isActive():   # ausstehende Musik-Einstellungen nicht verlieren
            self._save_timer.stop()
            self.data.save()
        try:
            self._music.state_changed.disconnect(self._music_refresh)
        except (TypeError, RuntimeError):
            pass
        super().done(result)

    # ---------------------------------------------------------------- Helfer
    @staticmethod
    def _slider_row(lo: int, hi: int, value: int, unit: str):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setObjectName("SizeSlider")
        slider.setRange(lo, hi)
        slider.setValue(max(lo, min(hi, value)))
        label = QLabel(f"{slider.value()} {unit}")
        label.setMinimumWidth(48)
        slider.valueChanged.connect(lambda v: label.setText(f"{v} {unit}"))
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(slider, 1)
        h.addWidget(label)
        return slider, row

    def _bg_path(self) -> str:
        if self._bg_src:
            return self._bg_src
        return self.data.abs_path(self._bg_rel) if self._bg_rel else ""

    def _update_bg_preview(self) -> None:
        path = self._bg_path()
        if path and os.path.isfile(path):
            self.bg_preview.setText("")
            self.bg_preview.setPixmap(make_cover_pixmap(path, *self.BG_PREVIEW, "", "", radius=10))
        else:
            self.bg_preview.setPixmap(QPixmap())
            self.bg_preview.setText(tr("Kein Hintergrundbild\n(Theme-Farbverlauf)"))

    def _choose_background(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Hintergrundbild auswählen"), _start_dir(self._bg_src), image_filter())
        if path:
            self._bg_src = path
            self._update_bg_preview()

    def _clear_background(self) -> None:
        self._bg_src = ""
        self._bg_rel = ""
        self._update_bg_preview()

    # ------------------------------------------------------------- Speichern
    def _save(self) -> None:
        st = self.data.settings
        old_bg = st.get("background", "")
        new_bg = self._bg_rel
        if self._bg_src:
            try:
                new_bg = self.data.import_background(self._bg_src)
            except ValueError as exc:
                QMessageBox.warning(self, tr("Hintergrundbild"), str(exc))
                return
        if old_bg and old_bg != new_bg:
            self.data.remove_background(old_bg)

        st["language"] = self.lang_combo.currentData()
        st["custom_themes"] = set_custom_themes(self._custom_themes)   # auch THEMES aktualisieren
        theme = self.theme_combo.currentText()
        st["theme"] = theme if theme in styles.THEMES else DEFAULT_THEME
        st["background"] = new_bg
        st["background_dim"] = self.dim_slider.value()
        st["tile_scale"] = self.size_slider.value() / 100
        st["favorites_first"] = self.fav_first.isChecked()
        st["minimize_on_launch"] = self.minimize.isChecked()
        added, removed = self.emu_panel.custom_changes()
        self.data.apply_custom_emulators(added, removed)       # zuerst: neue Emulatoren anlegen/entfernen
        self.data.set_emulator_colors(self.emu_panel.color_changes())
        paths, args, apply_to = self.emu_panel.values()
        paths = {n: p for n, p in paths.items() if n in EMULATORS}
        args = {n: a for n, a in args.items() if n in EMULATORS}
        self.data.set_emulator_config(paths, args, apply_to)   # speichert auch settings
        self.accept()
