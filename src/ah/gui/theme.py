from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication


# First GUI pass: establish one visual language without touching AH Core logic.
WINDOW_BG = "#0b0f14"
PANEL_BG = "#111720"
PANEL_BG_ALT = "#151d27"
INPUT_BG = "#0c1219"
BORDER = "#263241"
BORDER_HOVER = "#3a4a5f"
TEXT = "#e7edf5"
TEXT_MUTED = "#8f9bad"
ACCENT = "#49a6ff"
ACCENT_HOVER = "#66b5ff"
ACCENT_PRESSED = "#2d83d5"
DANGER = "#ff5d62"
SUCCESS = "#39d98a"
WARNING = "#ffbd5c"


def apply_theme(app: QApplication) -> None:
    """Apply the first-pass desktop theme for the AG Memory GUI.

    This function is intentionally presentation-only: it changes Qt palette/QSS,
    never runtime state, AH data, graph semantics, or cognitive logic.
    """
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(WINDOW_BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(INPUT_BG))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(PANEL_BG_ALT))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(PANEL_BG_ALT))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(PANEL_BG))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link, QColor(ACCENT_HOVER))
    app.setPalette(palette)

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    app.setStyleSheet(
        f"""
        QWidget {{
            color: {TEXT};
            background: {PANEL_BG};
        }}

        QMainWindow {{
            background: {WINDOW_BG};
        }}

        QToolBar {{
            background: {WINDOW_BG};
            border: none;
            border-bottom: 1px solid {BORDER};
            spacing: 6px;
            padding: 7px 10px;
        }}

        QToolBar::separator {{
            width: 1px;
            margin: 4px 6px;
            background: {BORDER};
        }}

        QLabel#appTitle {{
            color: {TEXT};
            background: transparent;
            font-size: 14px;
            font-weight: 800;
            letter-spacing: 1px;
            padding-right: 2px;
        }}

        QToolButton {{
            color: {TEXT};
            background: transparent;
            border: 1px solid transparent;
            border-radius: 7px;
            padding: 7px 11px;
            font-weight: 600;
        }}

        QToolButton:hover {{
            background: {PANEL_BG_ALT};
            border-color: {BORDER_HOVER};
        }}

        QToolButton:pressed {{
            background: {ACCENT_PRESSED};
            border-color: {ACCENT_PRESSED};
        }}

        QLabel#workspaceModeLabel {{
            color: {TEXT_MUTED};
            background: transparent;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 1px;
            padding-left: 2px;
            padding-right: 2px;
        }}

        QToolBar#runtimeToolbar QToolButton:checked {{
            color: #ffffff;
            background: {ACCENT_PRESSED};
            border-color: {ACCENT};
        }}

        QToolBar#runtimeToolbar QToolButton:checked:hover {{
            background: {ACCENT};
        }}

        QDockWidget {{
            color: {TEXT};
            background: {PANEL_BG};
            border: 1px solid {BORDER};
        }}

        QDockWidget::title {{
            background: {PANEL_BG_ALT};
            text-align: left;
            padding: 9px 11px;
            border-bottom: 1px solid {BORDER};
            font-weight: 700;
        }}

        QDockWidget::close-button,
        QDockWidget::float-button {{
            background: transparent;
            border: none;
        }}

        QFrame#runtimeCard {{
            background: {PANEL_BG_ALT};
            border: 1px solid {BORDER};
            border-radius: 8px;
        }}

        QFrame#runtimeMetric {{
            background: {INPUT_BG};
            border: 1px solid {BORDER};
            border-radius: 7px;
        }}

        QLabel#runtimeMetricTitle,
        QLabel#runtimeFieldTitle,
        QLabel#runtimeSectionTitle {{
            color: {TEXT_MUTED};
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 0.6px;
        }}

        QLabel#runtimeMetricValue {{
            color: {TEXT};
            font-size: 16px;
            font-weight: 800;
        }}

        QLabel#runtimeFieldValue {{
            color: {TEXT};
            font-size: 12px;
            font-weight: 600;
        }}

        QLabel#runtimeStatus {{
            min-width: 76px;
            max-width: 96px;
            padding: 6px 10px;
            border-radius: 10px;
            font-size: 11px;
            font-weight: 900;
            background: {BORDER};
            color: {TEXT};
        }}

        QLabel#runtimeStatus[state="running"] {{
            background: {SUCCESS};
            color: #07110b;
        }}

        QLabel#runtimeStatus[state="stopped"] {{
            background: {BORDER};
            color: {TEXT_MUTED};
        }}

        QLabel#runtimeSummary {{
            color: {TEXT_MUTED};
            padding: 2px 4px;
        }}

        QPlainTextEdit#runtimePending {{
            min-height: 72px;
            background: {INPUT_BG};
        }}

        QListWidget#runtimeWorkspaceList {{
            background: {INPUT_BG};
            border: 1px solid {BORDER};
            border-radius: 7px;
            padding: 4px;
        }}

        QListWidget#runtimeWorkspaceList::item {{
            padding: 5px 6px;
            border-radius: 5px;
        }}

        QListWidget#runtimeWorkspaceList::item:hover {{
            background: {PANEL_BG_ALT};
        }}

        QFrame#graphToolbar {{
            background: {PANEL_BG_ALT};
            border: 1px solid {BORDER};
            border-radius: 9px;
        }}

        QFrame#graphHud {{
            background: {WINDOW_BG};
            border: 1px solid {BORDER};
            border-radius: 8px;
        }}

        QLabel#graphStats {{
            color: {TEXT};
            font-weight: 700;
            padding: 2px 4px;
        }}

        QLabel#graphHint {{
            color: {TEXT_MUTED};
            padding: 2px 4px;
        }}

        QFrame#graphToolbar QLineEdit,
        QFrame#graphToolbar QComboBox {{
            background: {INPUT_BG};
            border-color: {BORDER_HOVER};
            padding: 6px 8px;
        }}

        QFrame#graphToolbar QComboBox::drop-down {{
            border: none;
            width: 22px;
        }}

        QFrame#graphToolbar QPushButton {{
            padding: 7px 12px;
        }}


        QMainWindow > QTabBar::tab,
        QMainWindow QTabBar::tab {{
            background: {PANEL_BG};
            color: {TEXT_MUTED};
            padding: 8px 13px;
            margin-right: 1px;
            border: 1px solid transparent;
            border-bottom: 2px solid transparent;
        }}

        QMainWindow > QTabBar::tab:hover,
        QMainWindow QTabBar::tab:hover {{
            color: {TEXT};
            background: {PANEL_BG_ALT};
        }}

        QMainWindow > QTabBar::tab:selected,
        QMainWindow QTabBar::tab:selected {{
            color: {TEXT};
            background: {PANEL_BG_ALT};
            border-bottom-color: {ACCENT};
        }}

        QTabWidget#leftWorkspaceTabs::pane,
        QTabWidget#rightWorkspaceTabs::pane {{
            border: none;
            background: {PANEL_BG};
        }}

        QTabWidget#leftWorkspaceTabs QTabBar::tab,
        QTabWidget#rightWorkspaceTabs QTabBar::tab {{
            min-width: 78px;
            padding: 9px 12px;
        }}

        QLabel#appSubtitle {{
            color: {TEXT_MUTED};
            background: transparent;
            font-size: 11px;
            font-weight: 500;
        }}

        QLabel {{
            background: transparent;
        }}

        QPlainTextEdit,
        QTextBrowser,
        QLineEdit,
        QComboBox,
        QSpinBox,
        QDoubleSpinBox {{
            background: {INPUT_BG};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 7px;
            padding: 7px 8px;
            selection-background-color: {ACCENT};
        }}

        QPlainTextEdit:focus,
        QTextBrowser:focus,
        QLineEdit:focus,
        QComboBox:focus,
        QSpinBox:focus,
        QDoubleSpinBox:focus {{
            border-color: {ACCENT};
        }}

        QPushButton {{
            background: {PANEL_BG_ALT};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 7px;
            padding: 8px 12px;
            font-weight: 600;
        }}

        QPushButton#primaryButton {{
            background: #1d73bd;
            border-color: #2d83d5;
        }}

        QPushButton#primaryButton:hover {{
            background: #2d83d5;
            border-color: #49a6ff;
        }}

        QPushButton#primaryButton:pressed {{
            background: #185b96;
        }}

        QPushButton:hover {{
            background: #1a2532;
            border-color: {BORDER_HOVER};
        }}

        QPushButton:pressed {{
            background: #1e2b3a;
        }}

        QPushButton:disabled {{
            color: #5b6674;
            background: #11161d;
            border-color: #1c2530;
        }}

        QScrollBar:vertical {{
            width: 10px;
            background: transparent;
            margin: 2px;
        }}

        QScrollBar::handle:vertical {{
            min-height: 28px;
            background: #2a3544;
            border-radius: 5px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: #39485a;
        }}

        QScrollBar:horizontal {{
            height: 10px;
            background: transparent;
            margin: 2px;
        }}

        QScrollBar::handle:horizontal {{
            min-width: 28px;
            background: #2a3544;
            border-radius: 5px;
        }}

        QTabWidget::pane {{
            border: 1px solid {BORDER};
            background: {PANEL_BG};
        }}

        QTabBar::tab {{
            background: {PANEL_BG};
            color: {TEXT_MUTED};
            padding: 8px 12px;
            border: none;
            border-bottom: 2px solid transparent;
        }}

        QTabBar::tab:hover {{
            color: {TEXT};
        }}

        QTabBar::tab:selected {{
            color: {TEXT};
            border-bottom-color: {ACCENT};
        }}

        QStatusBar {{
            background: {WINDOW_BG};
            color: {TEXT_MUTED};
            border-top: 1px solid {BORDER};
        }}

        QSplitter::handle {{
            background: {BORDER};
        }}

        QLabel#inspectorTitle {{
            color: {TEXT};
            font-size: 12px;
            font-weight: 900;
            letter-spacing: 1px;
        }}

        QLabel#inspectorSubtitle {{
            color: {TEXT_MUTED};
            padding-left: 2px;
            padding-bottom: 4px;
        }}

        QFrame#inspectorCard {{
            background: {PANEL_BG_ALT};
            border: 1px solid {BORDER};
            border-radius: 8px;
        }}

        QLabel#inspectorSectionTitle {{
            color: {ACCENT};
            font-size: 10px;
            font-weight: 900;
            letter-spacing: 0.8px;
            padding-bottom: 4px;
        }}

        QLabel#inspectorKey {{
            color: {TEXT_MUTED};
            font-size: 10px;
            font-weight: 700;
        }}

        QLabel#inspectorValue {{
            color: {TEXT};
            font-size: 11px;
            font-weight: 600;
        }}
        """
    )

