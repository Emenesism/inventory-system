from __future__ import annotations

LIGHT_THEME = """
* {
    font-family: "Poppins", "Manrope", "Segoe UI";
    font-size: 12px;
}
QMainWindow {
    background: #F5F7FA;
    color: #111827;
}
QFrame#Sidebar {
    background: #111827;
    border: none;
}
QFrame#HeaderBar {
    background: #FFFFFF;
    border-bottom: 1px solid #E5E7EB;
}
QLabel#AppTitle {
    font-size: 18px;
    font-weight: 600;
}
QLabel#StatusLabel {
    color: #6B7280;
}
QLabel#SidebarHint {
    color: #9CA3AF;
    font-size: 11px;
    padding-left: 36px;
}
QToolButton#ThemeButton {
    background: #EEF2FF;
    color: #1D4ED8;
    border-radius: 10px;
    padding: 6px 10px;
}
QToolButton#ThemeButton:hover {
    background: #E0E7FF;
}
QToolButton#SelectInventoryButton {
    background: #DBEAFE;
    color: #1D4ED8;
    border-radius: 10px;
    padding: 6px 10px;
}
QToolButton#SelectInventoryButton:hover {
    background: #BFDBFE;
}
QToolButton#SidebarButton {
    color: #E5E7EB;
    background: transparent;
    padding: 10px 12px;
    border-radius: 12px;
    text-align: left;
    font-size: 13px;
}
QToolButton#SidebarButton:hover {
    background: #1F2937;
}
QToolButton#SidebarButton:checked {
    background: #2563EB;
    color: #FFFFFF;
}
QFrame#Card {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 14px;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 10px;
    padding: 6px 10px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #2563EB;
}
QPushButton {
    background: #2563EB;
    color: #FFFFFF;
    border-radius: 10px;
    padding: 8px 14px;
}
QPushButton:hover {
    background: #1D4ED8;
}
QPushButton:disabled {
    background: #9CA3AF;
}
QTableView {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
    gridline-color: #E5E7EB;
    selection-background-color: #DBEAFE;
    selection-color: #111827;
}
QHeaderView::section {
    background: #F3F4F6;
    border: none;
    padding: 8px;
    font-weight: 600;
}
QFrame#Toast {
    background: rgba(17, 24, 39, 0.92);
    color: #FFFFFF;
    border-radius: 12px;
    padding: 10px 14px;
}
QFrame#Toast[toastType="success"] {
    background: #16A34A;
}
QFrame#Toast[toastType="error"] {
    background: #DC2626;
}
"""


DARK_THEME = """
* {
    font-family: "Poppins", "Manrope", "Segoe UI";
    font-size: 12px;
}
QMainWindow {
    background: #0F172A;
    color: #F8FAFC;
}
QFrame#Sidebar {
    background: #0B1220;
    border: none;
}
QFrame#HeaderBar {
    background: #111827;
    border-bottom: 1px solid #1F2937;
}
QLabel#AppTitle {
    font-size: 18px;
    font-weight: 600;
    color: #F8FAFC;
}
QLabel#StatusLabel {
    color: #9CA3AF;
}
QLabel#SidebarHint {
    color: #94A3B8;
    font-size: 11px;
    padding-left: 36px;
}
QToolButton#ThemeButton {
    background: #1F2937;
    color: #F8FAFC;
    border-radius: 10px;
    padding: 6px 10px;
}
QToolButton#ThemeButton:hover {
    background: #374151;
}
QToolButton#SelectInventoryButton {
    background: #1D4ED8;
    color: #FFFFFF;
    border-radius: 10px;
    padding: 6px 10px;
}
QToolButton#SelectInventoryButton:hover {
    background: #2563EB;
}
QToolButton#SidebarButton {
    color: #E5E7EB;
    background: transparent;
    padding: 10px 12px;
    border-radius: 12px;
    text-align: left;
    font-size: 13px;
}
QToolButton#SidebarButton:hover {
    background: #1F2937;
}
QToolButton#SidebarButton:checked {
    background: #2563EB;
    color: #FFFFFF;
}
QFrame#Card {
    background: #111827;
    border: 1px solid #1F2937;
    border-radius: 14px;
}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #0B1220;
    border: 1px solid #1F2937;
    border-radius: 10px;
    padding: 6px 10px;
    color: #F8FAFC;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #60A5FA;
}
QPushButton {
    background: #2563EB;
    color: #FFFFFF;
    border-radius: 10px;
    padding: 8px 14px;
}
QPushButton:hover {
    background: #1D4ED8;
}
QPushButton:disabled {
    background: #374151;
}
QTableView {
    background: #0B1220;
    border: 1px solid #1F2937;
    border-radius: 12px;
    gridline-color: #1F2937;
    color: #E5E7EB;
    selection-background-color: #1D4ED8;
    selection-color: #F8FAFC;
    alternate-background-color: #0F1B2D;
}
QTableView::item {
    background: #0B1220;
    color: #E5E7EB;
    padding: 4px;
}
QTableView::item:alternate {
    background: #0F1B2D;
    color: #E5E7EB;
}
QTableView::item:selected {
    background: #1D4ED8;
    color: #F8FAFC;
}
QHeaderView::section {
    background: #111827;
    border: none;
    padding: 8px;
    font-weight: 600;
    color: #F8FAFC;
}
QFrame#Toast {
    background: rgba(15, 23, 42, 0.95);
    color: #FFFFFF;
    border-radius: 12px;
    padding: 10px 14px;
}
QFrame#Toast[toastType="success"] {
    background: #16A34A;
}
QFrame#Toast[toastType="error"] {
    background: #DC2626;
}
"""


def get_stylesheet(theme: str) -> str:
    return DARK_THEME if theme == "dark" else LIGHT_THEME
