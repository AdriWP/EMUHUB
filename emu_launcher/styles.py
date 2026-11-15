"""Design: mehrere Farb-Themes (Fusion-Palette + Qt StyleSheet mit Farbverläufen).

Eigene Themes legt man in den Einstellungen an (Farbwähler); sie liegen in settings["custom_themes"]
und werden mit `set_custom_themes` in THEMES eingehängt. Fest eingebaute: BUILTIN_THEMES.
"""
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from data_manager import EMULATORS

# bg/bg2      = Fensterhintergrund (Verlauf von oben links nach unten rechts)
# surface     = Header & Seitenleiste
# card        = Spielekacheln
# input       = Eingabefelder
# accent/accent2 = Akzent-Verlauf (Buttons, Auswahl, Fokus)
BUILTIN_THEMES: dict[str, dict[str, str]] = {
    "Midnight Blue": {
        "bg": "#0b1020", "bg2": "#161032", "surface": "#121831", "card": "#182042",
        "input": "#1a2246", "border": "#2a3563", "text": "#e8ecff", "muted": "#8f9bc7",
        "accent": "#4f7bff", "accent2": "#9b5cff",
    },
    "Arcade Rot": {
        "bg": "#120b0d", "bg2": "#2a0d12", "surface": "#1b1013", "card": "#24141a",
        "input": "#2a171d", "border": "#4a2430", "text": "#fff0f2", "muted": "#c79aa4",
        "accent": "#e60012", "accent2": "#ff5a36",
    },
    "Neon Arcade": {
        "bg": "#07060f", "bg2": "#1a0730", "surface": "#100c22", "card": "#171233",
        "input": "#1b1540", "border": "#3a2a73", "text": "#f2edff", "muted": "#a596d6",
        "accent": "#ff2bd6", "accent2": "#00e5ff",
    },
    "Aurora": {
        "bg": "#06120f", "bg2": "#0a1f2a", "surface": "#0d1c1d", "card": "#122826",
        "input": "#132b2b", "border": "#21494a", "text": "#e9fffa", "muted": "#8cc2b8",
        "accent": "#10b981", "accent2": "#06b6d4",
    },
    "Sunset": {
        "bg": "#140b10", "bg2": "#2b1222", "surface": "#1d1018", "card": "#271520",
        "input": "#2c1824", "border": "#55293f", "text": "#fff1ea", "muted": "#d4a3a8",
        "accent": "#f97316", "accent2": "#ec4899",
    },
    "Graphit (schlicht)": {
        "bg": "#0f1117", "bg2": "#0f1117", "surface": "#151821", "card": "#171b26",
        "input": "#1a1e2a", "border": "#262c3d", "text": "#e5e7eb", "muted": "#8b93a7",
        "accent": "#5b8cff", "accent2": "#5b8cff",
    },
}
DEFAULT_THEME = "Midnight Blue"
THEME_KEYS = ("bg", "bg2", "surface", "card", "input", "border", "text", "muted", "accent", "accent2")
MAX_THEME_NAME = 30
# Alle Themes (eingebaute + eigene). Wird nur vorhanden verändert (nie neu zuweisen), damit Importe aktuell bleiben.
THEMES: dict[str, dict[str, str]] = {k: dict(v) for k, v in BUILTIN_THEMES.items()}


def _mix(a: str, b: str, t: float) -> str:
    """Mischt zwei Farben: t=0 -> a, t=1 -> b."""
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * t), round(ca.green() + (cb.green() - ca.green()) * t),
                  round(ca.blue() + (cb.blue() - ca.blue()) * t)).name()


def derive_theme(bg: str, text: str, accent: str, accent2: str) -> dict[str, str]:
    """Aus vier Grundfarben ein vollständiges Theme ableiten (Flächen = Hintergrund leicht zur Textfarbe gemischt)."""
    return {
        "bg": QColor(bg).name(), "bg2": _mix(bg, accent2, 0.16),
        "surface": _mix(bg, text, 0.05), "card": _mix(bg, text, 0.09), "input": _mix(bg, text, 0.11),
        "border": _mix(bg, accent, 0.28), "text": QColor(text).name(), "muted": _mix(text, bg, 0.42),
        "accent": QColor(accent).name(), "accent2": QColor(accent2).name(),
    }


def clean_custom_themes(raw) -> dict[str, dict[str, str]]:
    """Nur vollständige, gültige eigene Themes mit freiem Namen behalten (kaputte Einträge werden verworfen)."""
    out: dict[str, dict[str, str]] = {}
    if not isinstance(raw, dict):
        return out
    builtin = {n.lower() for n in BUILTIN_THEMES}
    for name, t in raw.items():
        name = str(name).strip()
        if (not name or len(name) > MAX_THEME_NAME or name.lower() in builtin or not isinstance(t, dict)
                or any(not (isinstance(t.get(k), str) and QColor(t[k]).isValid()) for k in THEME_KEYS)):
            continue
        out[name] = {k: QColor(t[k]).name() for k in THEME_KEYS}
    return out


def set_custom_themes(raw) -> dict[str, dict[str, str]]:
    """Hängt eigene Themes in THEMES ein (ersetzt vorherige eigene) und gibt die bereinigte Liste zurück."""
    custom = clean_custom_themes(raw)
    THEMES.clear()
    THEMES.update({k: dict(v) for k, v in BUILTIN_THEMES.items()})
    THEMES.update(custom)
    return custom


def rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {int(alpha * 255)})"


def _lighter(hex_color: str, factor: int = 115) -> str:
    return QColor(hex_color).lighter(factor).name()


def apply_theme(app: QApplication, name: str) -> str:
    """Wendet ein Theme an und gibt den tatsächlich verwendeten Namen zurück."""
    if name not in THEMES:
        name = DEFAULT_THEME
    t = THEMES[name]
    app.setStyle("Fusion")
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(t["bg"]))
    p.setColor(QPalette.ColorRole.WindowText, QColor(t["text"]))
    p.setColor(QPalette.ColorRole.Base, QColor(t["input"]))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(t["surface"]))
    p.setColor(QPalette.ColorRole.Text, QColor(t["text"]))
    p.setColor(QPalette.ColorRole.Button, QColor(t["card"]))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(t["text"]))
    p.setColor(QPalette.ColorRole.Highlight, QColor(t["accent"]))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(t["input"]))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(t["text"]))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(t["muted"]))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t["muted"]))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(t["muted"]))
    app.setPalette(p)
    app.setStyleSheet(build_qss(t))
    return name


def build_qss(t: dict[str, str]) -> str:
    bg, bg2, surface, card = t["bg"], t["bg2"], t["surface"], t["card"]
    inp, border, text, muted = t["input"], t["border"], t["text"], t["muted"]
    acc, acc2 = t["accent"], t["accent2"]
    acc_grad = f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {acc}, stop:1 {acc2})"
    acc_grad_hover = (f"qlineargradient(x1:0, y1:0, x2:1, y2:0, "
                      f"stop:0 {_lighter(acc)}, stop:1 {_lighter(acc2)})")

    per_emu = []
    for emu, color in EMULATORS.items():
        per_emu.append(
            f'QPushButton#FilterButton[emu="{emu}"]:checked {{ background-color: {color}; '
            f'border-color: {color}; color: #ffffff; }}\n'
            f'QPushButton#FilterButton[emu="{emu}"]:hover:!checked {{ border-color: {color}; '
            f'color: {color}; }}\n'
            f'#GameCard[emu="{emu}"]:hover {{ border: 1px solid {color}; '
            f'background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, '
            f'stop:0 {rgba(color, 0.16)}, stop:1 {card}); }}\n'
            f'#GameCard[emu="{emu}"][selected="true"] {{ border: 2px solid {color}; '
            f'background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, '
            f'stop:0 {rgba(color, 0.30)}, stop:1 {card}); }}'
        )
    per_emu_qss = "\n".join(per_emu)

    return f"""
* {{
    font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif;
    font-size: 10pt;
    color: {text};
}}
QMainWindow {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {bg}, stop:1 {bg2});
}}
QDialog, QMessageBox {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {surface}, stop:1 {bg2});
}}
QLabel {{ background: transparent; }}
QToolTip {{ background-color: {inp}; color: {text}; border: 1px solid {border}; padding: 4px 6px; }}

/* ---------- Header ---------- */
#Header {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {rgba(surface, 0.95)}, stop:0.6 {rgba(acc, 0.10)}, stop:1 {rgba(acc2, 0.22)});
    border-bottom: 1px solid {border};
}}
#AppTitle {{ font-size: 17pt; font-weight: 800; color: #ffffff; }}
#AppSubtitle, #CountLabel {{ color: {muted}; font-size: 9pt; }}
#AccentLine {{ background-color: {acc_grad}; border: none; }}

/* ---------- Eingabefelder ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {{
    background-color: {inp};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {acc};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{ border: 1px solid {acc}; }}
QLineEdit:read-only {{ background-color: {rgba(bg, 0.6)}; }}
QLineEdit#SearchField {{ border-radius: 18px; padding: 8px 16px; min-width: 260px; }}
QComboBox#ThemeCombo {{ border-radius: 18px; padding: 7px 14px; min-width: 150px; }}
QComboBox QAbstractItemView {{
    background-color: {inp}; border: 1px solid {border};
    selection-background-color: {acc}; outline: 0; padding: 4px;
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background-color: {card};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 7px 14px;
}}
QPushButton:hover {{ background-color: {_lighter(card, 125)}; border-color: {acc}; }}
QPushButton:pressed {{ background-color: {bg}; }}
QPushButton:disabled {{ color: {muted}; border-color: {card}; }}
QPushButton#PrimaryButton {{
    background-color: {acc_grad}; border: none; color: #ffffff; font-weight: 700;
    padding: 8px 16px;
}}
QPushButton#PrimaryButton:hover {{ background-color: {acc_grad_hover}; }}
QPushButton#PrimaryButton:pressed {{ background-color: {acc}; }}
QPushButton#DangerButton {{ background-color: transparent; border: 1px solid #b91c1c; color: #f87171; }}
QPushButton#DangerButton:hover {{ background-color: rgba(185, 28, 28, 60); }}
QPushButton#FilterButton {{
    background-color: {rgba(card, 0.6)};
    border: 1px solid {border};
    border-radius: 15px;
    padding: 5px 16px;
}}
QPushButton#FilterButton:checked {{ font-weight: 700; }}
QPushButton#FilterButton[emu="Alle"]:checked {{
    background-color: {acc_grad}; border: 1px solid transparent; border-radius: 15px; color: #ffffff;
}}
{per_emu_qss}

/* ---------- Einstellungen: Tabs & Checkboxen ---------- */
QTabWidget::pane {{ border: 1px solid {border}; border-radius: 10px; background: {rgba(bg, 0.55)}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {muted}; padding: 9px 18px; margin-right: 4px;
    border: 1px solid transparent; border-top-left-radius: 8px; border-top-right-radius: 8px;
}}
QTabBar::tab:hover {{ color: {text}; }}
QTabBar::tab:selected {{ color: #ffffff; background: {rgba(acc, 0.22)}; border-color: {border}; border-bottom-color: transparent; font-weight: 700; }}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {border}; background: {inp}; }}
QCheckBox::indicator:checked {{ background: {acc_grad}; border-color: {acc}; }}
#SettingsButton {{ font-weight: 600; }}

/* ---------- Emulator-Einrichtung ---------- */
QListWidget#EmuList {{ background-color: {rgba(bg, 0.55)}; border: 1px solid {border}; border-radius: 10px; padding: 6px; outline: 0; }}
QListWidget#EmuList::item {{ padding: 11px 10px; border-radius: 8px; font-weight: 700; }}
QListWidget#EmuList::item:hover {{ background-color: {rgba(acc, 0.12)}; }}
QListWidget#EmuList::item:selected {{ background-color: {rgba(acc, 0.28)}; }}

/* ---------- Screenshot-Galerie ---------- */
QToolButton#ShotThumb {{ background-color: {rgba(card, 0.85)}; border: 2px solid {border}; border-radius: 12px; padding: 6px; }}
QToolButton#ShotThumb:hover {{ border-color: {acc}; }}
QToolButton#ShotThumb:focus {{ border: 2px solid #ffffff; background-color: {rgba(acc, 0.20)}; }}
#ViewerDialog {{ background-color: #05060a; }}
#ViewerInfo {{ color: #cbd5e1; font-size: 10pt; }}
QPushButton#ViewerNav {{ font-size: 20pt; min-width: 54px; min-height: 90px; border-radius: 14px; background-color: rgba(255, 255, 255, 18); border: 1px solid rgba(255, 255, 255, 40); }}
QPushButton#ViewerNav:hover {{ background-color: {rgba(acc, 0.45)}; }}
QPushButton#ViewerNav:disabled {{ color: rgba(255, 255, 255, 50); background-color: transparent; }}

/* ---------- Favoriten & Sortierung ---------- */
#FavStar {{
    background-color: rgba(0, 0, 0, 150); border-radius: 15px;
    color: #ffffff; font-size: 14pt;
}}
#FavStar[active="true"] {{ color: #facc15; background-color: rgba(0, 0, 0, 170); }}
QPushButton#FavButton {{ font-size: 14pt; padding: 3px 0; }}
QPushButton#FavButton:checked {{ color: #facc15; border-color: #facc15; background-color: rgba(250, 204, 21, 30); }}
QPushButton#FilterButton[emu="Fav"]:checked {{ background-color: #eab308; border-color: #eab308; color: #1a1300; }}
QPushButton#FilterButton[emu="Fav"]:hover:!checked {{ border-color: #facc15; color: #facc15; }}
#FilterSeparator {{ background-color: {border}; border: none; }}
QComboBox#SortCombo {{ border-radius: 15px; padding: 5px 12px; min-width: 150px; }}

/* ---------- Größenregler ---------- */
QSlider#SizeSlider::groove:horizontal {{ height: 4px; background: {border}; border-radius: 2px; }}
QSlider#SizeSlider::sub-page:horizontal {{ background: {acc_grad}; border-radius: 2px; }}
QSlider#SizeSlider::handle:horizontal {{
    background: #ffffff; border: 2px solid {acc}; width: 12px; height: 12px;
    margin: -6px 0; border-radius: 8px;
}}

/* ---------- Bibliothek ---------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > #qt_scrollarea_viewport {{ background: transparent; }}
#LibraryContainer, #EmptyPage, #DetailsInner {{ background: transparent; }}
#EmptyState {{ color: {muted}; font-size: 12pt; }}

#GameCard {{
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {_lighter(card, 112)}, stop:1 {card});
    border: 1px solid {rgba(border, 0.8)};
    border-radius: 14px;
}}
#CardTitle {{ font-weight: 700; font-size: 10pt; color: #ffffff; }}
#GameCard[pad="true"][selected="true"] {{ border: 2px solid #ffffff; }}

/* ---------- Detail-Seitenleiste ---------- */
#DetailsPanel {{
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {rgba(acc, 0.10)}, stop:0.35 {rgba(surface, 0.92)}, stop:1 {rgba(surface, 0.96)});
    border-left: 1px solid {border};
}}
#DetailsTitle {{ font-size: 15pt; font-weight: 800; color: #ffffff; }}
#SectionLabel {{ color: {acc}; font-size: 8pt; font-weight: 800; letter-spacing: 1px; }}
#MetaLabel {{ color: {muted}; font-size: 9pt; }}
#Placeholder {{ color: {muted}; font-size: 11pt; }}
QPlainTextEdit#NotesView {{ background-color: {rgba(bg, 0.6)}; }}

/* ---------- Dialog ---------- */
#HintLabel {{ color: {muted}; font-size: 8pt; }}
#DialogTitle {{ font-size: 15pt; font-weight: 800; color: #ffffff; }}
#CoverPreview {{ background-color: {inp}; border: 1px dashed {border}; border-radius: 10px; }}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {border}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {acc}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {border}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

/* ---------- Menü & Statusleiste ---------- */
QMenu {{ background-color: {inp}; border: 1px solid {border}; padding: 4px; border-radius: 6px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {acc}; color: #ffffff; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 6px; }}
QStatusBar {{ background-color: {rgba(surface, 0.95)}; color: {muted}; border-top: 1px solid {border}; }}
QStatusBar QLabel {{ color: {muted}; }}
"""
