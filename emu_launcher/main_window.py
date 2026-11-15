"""Hauptfenster: Header mit Suche/Filter, Kachel-Bibliothek, Detail-Seitenleiste."""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractSpinBox, QApplication, QButtonGroup, QComboBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSlider, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

import sfx
from controller import GamepadController
from data_manager import EMULATORS, SORT_MODES, build_command, sort_games
from i18n import DEFAULT_LANGUAGE, get_language, set_language, tr
from dialogs import GameDialog, SettingsDialog
from emulators import ExeSearchWorker
from gallery import ScreenshotGalleryDialog, ThumbWorker
from styles import apply_theme
from widgets import BackgroundWidget, DetailsPanel, FlowLayout, GameCard, ask_yes_no, screen_dpr

ALL_FILTER = "Alle"


class MainWindow(QMainWindow):
    def __init__(self, data_manager):
        super().__init__()
        self.setProperty("hover_sfx", True)   # Maus-Hover in diesem Fenster macht den Blasen-Klang (sfx.py)
        self.data = data_manager
        self.cards: dict[str, GameCard] = {}
        self.selected_id: str | None = None
        self.current_filter = ALL_FILTER
        self.favorites_only = False
        self.sort_mode = self.data.settings.get("sort_mode", "name")
        if self.sort_mode not in SORT_MODES:
            self.sort_mode = "name"
        try:
            self.tile_scale = min(1.6, max(0.6, float(self.data.settings.get("tile_scale", 1.0))))
        except (TypeError, ValueError):
            self.tile_scale = 1.0
        self._resize_timer = QTimer(self, singleShot=True, interval=150)
        self._resize_timer.timeout.connect(self._apply_tile_scale)

        self.setWindowTitle("EMUHUB – Switch & 3DS")
        self.resize(1360, 860)
        self.setMinimumHeight(600)  # Mindestbreite ergibt sich aus dem Layout (Filterleiste)

        central = BackgroundWidget()
        self.background = central
        self.setCentralWidget(central)
        self._apply_background()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        accent_line = QFrame()
        accent_line.setObjectName("AccentLine")
        accent_line.setFixedHeight(2)
        root.addWidget(accent_line)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, 1)

        # Bibliothek
        self.library_stack = QStackedWidget()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().installEventFilter(self)  # Strg+Mausrad = Kachelgröße
        self.container = QWidget()
        self.container.setObjectName("LibraryContainer")
        self.flow = FlowLayout(self.container, margin=26, h_spacing=18, v_spacing=20)
        self.scroll.setWidget(self.container)
        self.library_stack.addWidget(self.scroll)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("EmptyState")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_page = QWidget()
        empty_page.setObjectName("EmptyPage")
        ev = QVBoxLayout(empty_page)
        ev.addWidget(self.empty_label)
        self.library_stack.addWidget(empty_page)
        body.addWidget(self.library_stack, 1)

        # Seitenleiste
        self.details = DetailsPanel(self.data)
        self.details.launch_requested.connect(self.launch_game)
        self.details.edit_requested.connect(self.edit_game)
        self.details.delete_requested.connect(self.delete_game)
        self.details.favorite_requested.connect(self.toggle_favorite)
        self.details.screenshots_requested.connect(self.show_screenshots)
        body.addWidget(self.details)

        self.status_label = QLabel()
        self.statusBar().addPermanentWidget(self.status_label)

        QShortcut(QKeySequence.StandardKey.Find, self, activated=self._focus_search)
        QShortcut(QKeySequence.StandardKey.New, self, activated=self.add_game)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self,
                  activated=lambda: self.selected_id and self.delete_game(self.selected_id))
        QShortcut(QKeySequence(Qt.Key.Key_F5), self,
                  activated=lambda: self.selected_id and self.launch_game(self.selected_id))
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self._launch_selected_by_key)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, activated=self._launch_selected_by_key)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.open_settings)
        QShortcut(QKeySequence("Ctrl+D"), self,
                  activated=lambda: self.selected_id and self.toggle_favorite(self.selected_id))
        QShortcut(QKeySequence.StandardKey.ZoomIn, self,
                  activated=lambda: self.size_slider.setValue(self.size_slider.value() + 10))
        QShortcut(QKeySequence.StandardKey.ZoomOut, self,
                  activated=lambda: self.size_slider.setValue(self.size_slider.value() - 10))

        self.rebuild_cards()

        # Controller: Eingaben kommen als Signal und werden per Queue im GUI-Takt verarbeitet
        self.gamepad = GamepadController(gate=self._input_allowed, parent=self)
        self.gamepad.action.connect(self._on_gamepad_action, Qt.ConnectionType.QueuedConnection)
        self.gamepad.status.connect(lambda msg: self.statusBar().showMessage(msg, 6000))
        QApplication.instance().aboutToQuit.connect(self.gamepad.stop)
        QApplication.instance().aboutToQuit.connect(ThumbWorker.wait_all)
        QApplication.instance().aboutToQuit.connect(ExeSearchWorker.wait_all)
        self.gamepad.start()

    # ---------------------------------------------------------------- Header
    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        v = QVBoxLayout(header)
        v.setContentsMargins(26, 18, 26, 14)
        v.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(10)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel("🎮  EMUHUB")
        logo = self.data.base_dir / "assets" / "logo.png"   # optional: ersetzt den Schriftzug
        if logo.is_file() and not QPixmap(str(logo)).isNull():
            dpr = screen_dpr()
            pm = QPixmap(str(logo)).scaledToHeight(int(40 * dpr), Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            title.setText("")
            title.setPixmap(pm)
        title.setObjectName("AppTitle")
        subtitle = QLabel(tr("Switch- & 3DS-Bibliothek  ·  Doppelklick zum Starten"))
        subtitle.setObjectName("AppSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        top.addLayout(titles)
        top.addStretch(1)

        self.search = QLineEdit()
        self.search.setObjectName("SearchField")
        self.search.setPlaceholderText(tr("🔍  Spiele durchsuchen …  (Strg+F)"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(lambda _: self.apply_filter())
        top.addWidget(self.search)

        btn_settings = QPushButton(tr("⚙  Einstellungen"))
        btn_settings.setObjectName("SettingsButton")
        btn_settings.setToolTip(tr("Themes, Hintergrundbild, Kachelgröße, Emulator-Pfade (Strg+,)"))
        btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_settings.clicked.connect(self.open_settings)
        top.addWidget(btn_settings)

        btn_add = QPushButton(tr("+  Spiel hinzufügen"))
        btn_add.setObjectName("PrimaryButton")
        btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_add.clicked.connect(self.add_game)
        top.addWidget(btn_add)
        v.addLayout(top)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)
        for name in [ALL_FILTER, *EMULATORS.keys()]:
            b = QPushButton(tr(name) if name == ALL_FILTER else name)
            b.setObjectName("FilterButton")
            b.setProperty("emu", name)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setChecked(name == ALL_FILTER)
            self.filter_group.addButton(b)
            filters.addWidget(b)
        self.filter_group.buttonClicked.connect(self._on_filter_clicked)

        sep = QFrame()
        sep.setObjectName("FilterSeparator")
        sep.setFixedSize(1, 22)
        filters.addSpacing(4)
        filters.addWidget(sep)
        filters.addSpacing(4)
        self.fav_button = QPushButton(tr("★  Favoriten"))
        self.fav_button.setObjectName("FilterButton")
        self.fav_button.setProperty("emu", "Fav")
        self.fav_button.setCheckable(True)
        self.fav_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fav_button.setToolTip(tr("Nur Favoriten anzeigen (kombinierbar mit dem Emulator-Filter)"))
        self.fav_button.toggled.connect(self._on_favorites_toggled)
        filters.addWidget(self.fav_button)
        filters.addStretch(1)

        sort_label = QLabel(tr("Sortieren"))
        sort_label.setObjectName("CountLabel")
        filters.addWidget(sort_label)
        self.sort_combo = QComboBox()
        self.sort_combo.setObjectName("SortCombo")
        for key, label in SORT_MODES.items():
            self.sort_combo.addItem(tr(label), key)
        self.sort_combo.setCurrentIndex(max(0, self.sort_combo.findData(self.sort_mode)))
        self.sort_combo.setToolTip(tr("Favoriten stehen immer oben"))
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        filters.addWidget(self.sort_combo)
        filters.addSpacing(16)
        size_icon = QLabel(tr("🔍 Größe"))
        size_icon.setObjectName("CountLabel")
        size_icon.setToolTip(tr("Kachelgröße (auch Strg + Mausrad oder Strg + / Strg -)"))
        filters.addWidget(size_icon)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setObjectName("SizeSlider")
        self.size_slider.setRange(60, 160)
        self.size_slider.setSingleStep(5)
        self.size_slider.setPageStep(10)
        self.size_slider.setFixedWidth(150)
        self.size_slider.setValue(int(round(self.tile_scale * 100)))
        self.size_slider.setToolTip(size_icon.toolTip())
        self.size_slider.valueChanged.connect(lambda _: self._resize_timer.start())
        filters.addWidget(self.size_slider)
        filters.addSpacing(16)

        self.count_label = QLabel()
        self.count_label.setObjectName("CountLabel")
        filters.addWidget(self.count_label)
        v.addLayout(filters)
        return header

    def _apply_background(self) -> None:
        st = self.data.settings
        self.background.set_background(self.data.abs_path(st.get("background", "")),
                                       int(st.get("background_dim", 55)))

    def _apply_tile_scale(self) -> None:
        self.tile_scale = self.size_slider.value() / 100
        self.data.set_setting("tile_scale", self.tile_scale)
        self.rebuild_cards()

    def eventFilter(self, obj, event):
        if (obj is self.scroll.viewport() and event.type() == QEvent.Type.Wheel
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            step = 5 if event.angleDelta().y() > 0 else -5
            self.size_slider.setValue(self.size_slider.value() + step)
            return True
        return super().eventFilter(obj, event)

    def _on_favorites_toggled(self, checked: bool) -> None:
        self.favorites_only = checked
        self.apply_filter()

    def _on_sort_changed(self, _index: int) -> None:
        self.sort_mode = self.sort_combo.currentData()
        self.data.set_setting("sort_mode", self.sort_mode)
        self.rebuild_cards()

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _on_filter_clicked(self, button: QPushButton) -> None:
        self.current_filter = button.property("emu")
        self.apply_filter()

    # ---------------------------------------------------------- Bibliothek
    def rebuild_cards(self) -> None:
        while (item := self.flow.takeAt(0)) is not None:
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        self.cards.clear()

        fav_first = bool(self.data.settings.get("favorites_first", True))
        for game in sort_games(self.data.games, self.sort_mode, fav_first):
            card = GameCard(game, self.data.abs_path(game["cover"]), self.tile_scale)
            card.clicked.connect(self.select_game)
            card.double_clicked.connect(self.launch_game)
            card.context_requested.connect(self._show_context_menu)
            card.favorite_toggled.connect(self.toggle_favorite)
            self.flow.addWidget(card)
            self.cards[game["id"]] = card

        if self.selected_id not in self.cards:
            self.selected_id = None
        self.select_game(self.selected_id)
        self.apply_filter()

    def apply_filter(self) -> None:
        text = self.search.text().strip().lower()
        visible = 0
        for card in self.cards.values():
            show = ((self.current_filter == ALL_FILTER or card.emulator == self.current_filter)
                    and (not text or text in card.search_text)
                    and (not self.favorites_only or card.favorite))
            card.setVisible(show)
            visible += show
        self.flow.invalidate()
        self.container.updateGeometry()

        total = len(self.cards)
        self.count_label.setText(tr("{visible} von {total} Spiel" if total == 1 else "{visible} von {total} Spielen",
                                    visible=visible, total=total))
        self.status_label.setText(tr("{total} Spiel in der Bibliothek" if total == 1 else "{total} Spiele in der Bibliothek",
                                     total=total))
        if visible:
            self.library_stack.setCurrentIndex(0)
        else:
            self.empty_label.setText(
                tr("Noch keine Spiele.\nKlicke auf „+ Spiel hinzufügen“, um loszulegen.")
                if total == 0 else
                tr("Noch keine Favoriten.\nKlicke auf den ☆ einer Kachel, um ein Spiel zu markieren.")
                if self.favorites_only and not any(g.get("favorite") for g in self.data.games)
                else tr("Keine Spiele für diesen Filter / diese Suche gefunden."))
            self.library_stack.setCurrentIndex(1)

    def select_game(self, game_id: str | None) -> None:
        if self.selected_id in self.cards:
            self.cards[self.selected_id].set_selected(False)
            self.cards[self.selected_id].set_pad_focus(False)
        self.selected_id = game_id
        if game_id in self.cards:
            self.cards[game_id].set_selected(True)
            self.details.show_game(self.data.get_game(game_id))
        else:
            self.details.clear()

    # ------------------------------------------------------- Controller / Tastatur
    def _active_window(self):
        return QApplication.activeWindow()

    def _input_allowed(self) -> bool:
        """Controller nur beachten, wenn eines unserer Fenster aktiv ist – nicht,
        wenn gerade im Emulator gespielt wird."""
        return self._active_window() is not None

    def _launch_selected_by_key(self) -> None:
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QComboBox, QAbstractSpinBox, QTextEdit,
                              QPlainTextEdit, QAbstractButton, QSlider)):
            return  # Enter gehört dem fokussierten Bedienelement
        if self.selected_id:
            self.launch_game(self.selected_id)

    def _visible_cards(self) -> list[GameCard]:
        return [c for c in self.cards.values() if not c.isHidden()]

    def _pad_select(self, card: GameCard) -> None:
        self.select_game(card.game_id)
        card.set_pad_focus(True)
        sfx.effects().play_hover()   # Controller-Auswahl klingt wie Maus-Hover
        self.scroll.ensureWidgetVisible(card, 40, 40)

    def move_selection(self, direction: str) -> None:
        """Navigation im Raster. Zeilen/Positionen stammen aus dem Layout-Rechteck
        (nicht aus geometry(), das der Hover-Zoom verändert)."""
        cards = self._visible_cards()
        if not cards:
            return
        self.flow.activate()
        cur = self.cards.get(self.selected_id)
        if cur is None or cur.isHidden():
            self._pad_select(cards[0])
            return
        i = cards.index(cur)
        if direction in ("left", "right"):
            j = max(0, i - 1) if direction == "left" else min(len(cards) - 1, i + 1)
            target = cards[j]
        else:
            tops = sorted({c._layout_rect.top() for c in cards})
            row = tops.index(cur._layout_rect.top())
            row += -1 if direction == "up" else 1
            if not 0 <= row < len(tops):
                return
            cx = cur._layout_rect.center().x()
            candidates = [c for c in cards if c._layout_rect.top() == tops[row]]
            target = min(candidates, key=lambda c: abs(c._layout_rect.center().x() - cx))
        if target is not cur:
            self._pad_select(target)

    def step_filter(self, step: int) -> None:
        buttons = self.filter_group.buttons()
        cur = next((k for k, b in enumerate(buttons) if b.isChecked()), 0)
        buttons[(cur + step) % len(buttons)].click()
        sfx.effects().play_hover()
        cards = self._visible_cards()
        sel = self.cards.get(self.selected_id)
        if cards and (sel is None or sel.isHidden()):
            self._pad_select(cards[0])

    def _on_gamepad_action(self, action: str) -> None:
        win = self._active_window()
        if win is None:
            return
        popup = QApplication.activePopupWidget()
        if popup is not None:                      # offenes Kontextmenü
            if action == "b":
                popup.close()
            return
        modal = QApplication.activeModalWidget()
        if modal is not None:                      # offener Dialog / Meldung
            handler = getattr(modal, "handle_pad", None)   # z. B. Screenshot-Galerie
            if handler is not None and handler(action):
                return
            if action == "b":
                self._close_modal(modal)
            elif action == "a" and isinstance(modal, QMessageBox):
                btn = modal.defaultButton() or (modal.buttons() or [None])[0]
                if btn is not None:
                    btn.click()
            return
        if win is not self:
            return
        if action in ("up", "down", "left", "right"):
            self.move_selection(action)
        elif action == "a":
            if self.selected_id:
                self.launch_game(self.selected_id)
        elif action in ("l1", "r1"):
            self.step_filter(-1 if action == "l1" else 1)

    @staticmethod
    def _close_modal(modal: QWidget) -> None:
        if isinstance(modal, QMessageBox):
            for std in (QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Close, QMessageBox.StandardButton.Ok):
                btn = modal.button(std)
                if btn is not None:
                    btn.click()
                    return
        if hasattr(modal, "reject"):
            modal.reject()
        else:
            modal.close()

    def _show_context_menu(self, game_id: str, pos: QPoint) -> None:
        game = self.data.get_game(game_id)
        if game is None:
            return
        menu = QMenu(self)
        act_launch = QAction(tr("▶  Starten"), menu)
        act_edit = QAction(tr("Bearbeiten …"), menu)
        act_shots = QAction("📷  Screenshots …", menu)
        act_shots.triggered.connect(lambda: self.show_screenshots(game_id))
        act_mods = QAction(tr("Mod-Ordner öffnen"), menu)
        act_mods.setEnabled(bool(game["mod_path"]))
        act_fav = QAction(tr("★  Aus Favoriten entfernen") if game.get("favorite")
                          else tr("☆  Zu Favoriten hinzufügen"), menu)
        act_fav.triggered.connect(lambda: self.toggle_favorite(game_id))
        act_delete = QAction(tr("Löschen"), menu)
        act_launch.triggered.connect(lambda: self.launch_game(game_id))
        act_edit.triggered.connect(lambda: self.edit_game(game_id))
        act_mods.triggered.connect(self.details.btn_mods.click)
        act_delete.triggered.connect(lambda: self.delete_game(game_id))
        menu.addAction(act_launch)
        menu.addAction(act_edit)
        menu.addAction(act_shots)
        menu.addAction(act_mods)
        menu.addAction(act_fav)
        menu.addSeparator()
        menu.addAction(act_delete)
        menu.exec(pos)

    # --------------------------------------------------------------- Aktionen
    def launch_game(self, game_id: str) -> None:
        game = self.data.get_game(game_id)
        if game is None:
            return
        emu_name = game["emulator"]
        emu_path = self.data.resolve_emulator_path(game)
        rom = game["rom_path"]

        if not emu_path or not os.path.isfile(emu_path):
            if ask_yes_no(self, tr("Emulator nicht gefunden"),
                          tr("Für „{game}“ ist kein gültiger {emu}-Pfad hinterlegt:\n{path}\n\nJetzt bearbeiten?",
                             game=game["name"], emu=emu_name, path=emu_path or tr("(leer)"))):
                self.edit_game(game_id)
            return
        if not os.path.isfile(rom):
            QMessageBox.warning(self, tr("ROM nicht gefunden"),
                                tr("Die ROM-Datei existiert nicht:\n{rom}", rom=rom or tr("(leer)")))
            return

        try:
            cmd = build_command(emu_path, self.data.resolve_args(game), rom)
        except ValueError as exc:
            QMessageBox.warning(self, tr("Ungültige Start-Argumente"), str(exc))
            return

        try:
            subprocess.Popen(cmd, cwd=os.path.dirname(emu_path) or None)
        except OSError as exc:
            QMessageBox.critical(self, tr("Start fehlgeschlagen"),
                                 tr("{emu} konnte nicht gestartet werden:\n{exc}", emu=emu_name, exc=exc))
            return

        self.data.mark_played(game_id)
        if self.selected_id == game_id:
            self.details.show_game(game)
        self.statusBar().showMessage(tr("▶ {game} wird mit {emu} gestartet …", game=game["name"], emu=emu_name), 6000)
        if self.data.settings.get("minimize_on_launch", False):
            self.showMinimized()

    def show_screenshots(self, game_id: str) -> None:
        game = self.data.get_game(game_id)
        if game is not None:
            ScreenshotGalleryDialog(self.data, game, parent=self).exec()

    def toggle_favorite(self, game_id: str) -> None:
        game = self.data.get_game(game_id)
        if game is None:
            return
        fav = self.data.toggle_favorite(game_id)
        self.selected_id = game_id
        self.rebuild_cards()  # Favoriten wandern nach oben
        self.statusBar().showMessage(
            tr("★ „{game}“ zu Favoriten hinzugefügt.", game=game["name"]) if fav
            else tr("„{game}“ aus Favoriten entfernt.", game=game["name"]), 3000)

    def add_game(self) -> None:
        if not EMULATORS:   # frischer Start: erst einen Emulator anlegen
            QMessageBox.information(self, tr("Kein Emulator"), tr(
                "Noch kein Emulator eingerichtet.\n\nFüge zuerst einen hinzu: Einstellungen → Emulatoren → „＋ Emulator hinzufügen“."))
            self.open_settings()
            return
        dlg = GameDialog(self.data, parent=self)
        if dlg.exec() and dlg.result_data:
            game = self.data.add_game(dlg.result_data)
            self.selected_id = game["id"]
            self.rebuild_cards()
            self.statusBar().showMessage(tr("„{game}“ hinzugefügt.", game=game["name"]), 4000)

    def edit_game(self, game_id: str) -> None:
        game = self.data.get_game(game_id)
        if game is None:
            return
        dlg = GameDialog(self.data, game=game, parent=self)
        if dlg.exec() and dlg.result_data:
            self.data.update_game(game_id, dlg.result_data)
            self.selected_id = game_id
            self.rebuild_cards()
            self.statusBar().showMessage(tr("„{game}“ gespeichert.", game=dlg.result_data["name"]), 4000)

    def delete_game(self, game_id: str) -> None:
        game = self.data.get_game(game_id)
        if game is None:
            return
        if not ask_yes_no(
                self, tr("Spiel löschen"),
                tr("„{game}“ wirklich aus der Bibliothek entfernen?\n\n"
                   "ROM und Mods auf der Festplatte bleiben unangetastet.", game=game["name"]),
                default_yes=False):
            return
        self.data.delete_game(game_id)
        if self.selected_id == game_id:
            self.selected_id = None
        self.rebuild_cards()
        self.statusBar().showMessage(tr("„{game}“ entfernt.", game=game["name"]), 4000)

    def open_settings(self) -> None:
        old_language, old_emulators = get_language(), dict(EMULATORS)
        dlg = SettingsDialog(self.data, parent=self)
        if not dlg.exec():
            return
        st = self.data.settings
        language_changed = set_language(st.get("language", DEFAULT_LANGUAGE)) != old_language
        emulators_changed = dict(EMULATORS) != old_emulators
        if language_changed or emulators_changed:
            apply_theme(QApplication.instance(), st.get("theme", ""))   # Farben neuer Emulatoren ins QSS
            self._rebuild_for_language()   # Texte bzw. Filterknöpfe neu aufbauen
            return
        apply_theme(QApplication.instance(), st.get("theme", ""))
        self._apply_background()
        self.tile_scale = float(st.get("tile_scale", 1.0))
        self.size_slider.blockSignals(True)
        self.size_slider.setValue(int(round(self.tile_scale * 100)))
        self.size_slider.blockSignals(False)
        self.rebuild_cards()
        self.statusBar().showMessage(tr("Einstellungen gespeichert."), 4000)

    def _rebuild_for_language(self) -> None:
        """Sprache gewechselt: Fenster mit den neuen Texten neu aufbauen (Größe und Auswahl bleiben)."""
        app = QApplication.instance()
        geometry, selected = self.saveGeometry(), self.selected_id
        try:
            app.aboutToQuit.disconnect(self.gamepad.stop)
        except (TypeError, RuntimeError):
            pass
        self.gamepad.stop()                 # pygame wird vom neuen Fenster neu gestartet
        new = MainWindow(self.data)
        new.restoreGeometry(geometry)
        new.show()
        if selected in new.cards:
            new.select_game(selected)
        app._emu_main_window = new          # Referenz halten, sonst räumt Python das Fenster ab
        self.hide()
        self.deleteLater()
