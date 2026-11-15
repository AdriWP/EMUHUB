"""Eigenes Farb-Theme erstellen/bearbeiten: vier Grundfarben mit Farbwähler + Live-Vorschau.

Aus Hintergrund, Text, Akzent 1 und Akzent 2 werden alle weiteren Farben abgeleitet (`styles.derive_theme`).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from colorpicker import ColorPicker
from i18n import tr
from styles import BUILTIN_THEMES, DEFAULT_THEME, MAX_THEME_NAME, derive_theme


class ThemeEditorDialog(QDialog):
    """`result_values` = (Name, Theme-Dict mit allen Farben)."""

    def __init__(self, taken_names: set[str], name: str = "", base: dict | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self._taken = {n.lower() for n in taken_names}
        self.result_values: tuple[str, dict[str, str]] = ("", {})
        base = base or BUILTIN_THEMES[DEFAULT_THEME]
        self._colors = {k: base[k] for k in ("bg", "text", "accent", "accent2")}
        self._role = "bg"
        self.setWindowTitle(tr("Eigenes Theme bearbeiten") if name else tr("Eigenes Theme erstellen"))
        self.setMinimumSize(640, 440)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)
        title = QLabel(tr("🎨  Eigenes Theme"))
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        top = QHBoxLayout()
        top.addWidget(QLabel(tr("Name")))
        self.name_edit = QLineEdit(name)
        self.name_edit.setMaxLength(MAX_THEME_NAME)
        self.name_edit.setPlaceholderText(tr("z. B. Mein Theme"))
        top.addWidget(self.name_edit, 1)
        root.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(8)
        self.role_buttons: dict[str, QPushButton] = {}
        for role, label in (("bg", tr("Hintergrund")), ("text", tr("Schrift")),
                            ("accent", tr("Akzent 1")), ("accent2", tr("Akzent 2"))):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setAutoDefault(False)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, r=role: self._select_role(r))
            left.addWidget(b)
            self.role_buttons[role] = b
        left.addSpacing(8)
        self.preview = QFrame()
        self.preview.setMinimumSize(190, 150)
        pv = QVBoxLayout(self.preview)
        pv.setContentsMargins(12, 12, 12, 12)
        self.pv_card = QLabel(tr("Vorschau"))
        self.pv_card.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pv_muted = QLabel(tr("Zweitext"))
        self.pv_muted.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pv_button = QLabel(tr("▶  Spielen"))
        self.pv_button.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pv.addWidget(self.pv_card)
        pv.addWidget(self.pv_muted)
        pv.addStretch(1)
        pv.addWidget(self.pv_button)
        left.addWidget(self.preview, 1)
        body.addLayout(left)

        self.picker = ColorPicker(self._colors["bg"])
        self.picker.colorChanged.connect(self._picked)
        body.addWidget(self.picker, 1)
        root.addLayout(body, 1)

        self.error = QLabel()
        self.error.setStyleSheet("color: #f87171; font-weight: 600;")
        self.error.setWordWrap(True)
        self.error.hide()
        root.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        save = buttons.button(QDialogButtonBox.StandardButton.Save)
        save.setText(tr("Speichern"))
        save.setObjectName("PrimaryButton")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._select_role("bg")

    def theme(self) -> dict[str, str]:
        c = self._colors
        return derive_theme(c["bg"], c["text"], c["accent"], c["accent2"])

    def _select_role(self, role: str) -> None:
        self._role = role
        for r, b in self.role_buttons.items():
            b.setChecked(r == role)
        self.picker.setColor(self._colors[role], emit=False)
        self._paint()

    def _picked(self, color) -> None:
        self._colors[self._role] = color.name()
        self._paint()

    def _paint(self) -> None:
        t = self.theme()
        for r, b in self.role_buttons.items():
            col = self._colors[r]
            b.setStyleSheet(f"text-align: left; padding-left: 14px; border-left: 14px solid {col};")
        self.preview.setStyleSheet(
            f"QFrame {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {t['bg']}, stop:1 {t['bg2']}); "
            f"border: 1px solid {t['border']}; border-radius: 10px; }}"
            f"QLabel {{ background: transparent; border: none; }}")
        self.pv_card.setStyleSheet(f"background-color: {t['card']}; color: {t['text']}; border: 1px solid {t['border']}; "
                                   f"border-radius: 8px; padding: 10px; font-weight: 700;")
        self.pv_muted.setStyleSheet(f"color: {t['muted']};")
        self.pv_button.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {t['accent']}, stop:1 {t['accent2']}); "
            f"color: #ffffff; border-radius: 8px; padding: 8px; font-weight: 700;")

    def _accept(self) -> None:
        name = self.name_edit.text().strip()
        problem = None
        if not name:
            problem = tr("Bitte einen Namen eingeben.")
        elif name.lower() in self._taken:
            problem = tr("Ein Theme mit diesem Namen gibt es schon.")
        if problem:
            self.error.setText(problem)
            self.error.show()
            return
        self.result_values = (name, self.theme())
        self.accept()
