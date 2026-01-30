from __future__ import annotations

LIGHT_THEME = """
* {
    font-family: "Vazirmatn", "Manrope", "Segoe UI";
    font-size: 12px;
}
QMainWindow {
    background: #F5F7FA;
    color: #111827;
}
QWidget {
    color: #111827;
}
QDialog {
    background: #F5F7FA;
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
QLineEdit::placeholder, QPlainTextEdit::placeholder, QTextEdit::placeholder {
    color: #9CA3AF;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #2563EB;
}
QPlainTextEdit, QTextEdit {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 10px;
    padding: 8px 10px;
    color: #111827;
    selection-background-color: #DBEAFE;
    selection-color: #111827;
}
QScrollArea {
    background: transparent;
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
QPushButton[compact="true"] {
    background: #F3F4F6;
    color: #111827;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 4px 10px;
}
QPushButton[compact="true"]:hover {
    background: #E5E7EB;
}
QPushButton[variant="secondary"] {
    background: #E5E7EB;
    color: #111827;
    border: 1px solid #E5E7EB;
    border-radius: 10px;
    padding: 8px 14px;
}
QPushButton[variant="secondary"]:hover {
    background: #D1D5DB;
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
QTableWidget {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 12px;
    gridline-color: #E5E7EB;
    selection-background-color: #DBEAFE;
    selection-color: #111827;
    alternate-background-color: #F3F4F6;
}
QTableWidget::item {
    padding: 4px;
}
QTableWidget::item:selected {
    background: #DBEAFE;
    color: #111827;
}
QAbstractItemView {
    selection-background-color: #DBEAFE;
    selection-color: #111827;
}
QComboBox QAbstractItemView {
    background: #FFFFFF;
    color: #111827;
    border: 1px solid #E5E7EB;
    selection-background-color: #DBEAFE;
    selection-color: #111827;
}
QProgressBar {
    background: #F3F4F6;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    text-align: center;
    color: #111827;
}
QProgressBar::chunk {
    background: #2563EB;
    border-radius: 8px;
}
QLabel[textRole="muted"] {
    color: #6B7280;
}
QLabel[textRole="muted"][size="small"] {
    color: #6B7280;
    font-size: 11px;
}
QLabel[textRole="danger"] {
    color: #DC2626;
}
QLabel[textRole="danger"][size="small"] {
    color: #DC2626;
    font-size: 11px;
}
QDialog#LockDialog {
    background: rgba(15, 23, 42, 0.55);
}
QFrame#LockCard {
    background: #F8FAFC;
    border-radius: 16px;
    padding: 8px;
    min-width: 320px;
    border: 1px solid #E5E7EB;
}
QLabel#LockTitle {
    color: #0F172A;
    font-size: 18px;
    font-weight: 700;
}
QLabel#LockHint {
    color: #64748B;
    font-size: 12px;
}
QLabel#LockError {
    color: #DC2626;
    font-size: 12px;
}
QToolTip {
    background: #111827;
    color: #F9FAFB;
    border: 1px solid #1F2937;
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
    font-family: "Vazirmatn", "Manrope", "Segoe UI";
    font-size: 12px;
}
QMainWindow {
    background: #0F172A;
    color: #F8FAFC;
}
QWidget {
    color: #E5E7EB;
}
QDialog {
    background: #0F172A;
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
QLineEdit::placeholder, QPlainTextEdit::placeholder, QTextEdit::placeholder {
    color: #94A3B8;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #60A5FA;
}
QPlainTextEdit, QTextEdit {
    background: #0B1220;
    border: 1px solid #1F2937;
    border-radius: 10px;
    padding: 8px 10px;
    color: #E5E7EB;
    selection-background-color: #1D4ED8;
    selection-color: #F8FAFC;
}
QScrollArea {
    background: transparent;
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
QPushButton[compact="true"] {
    background: #1F2937;
    color: #F8FAFC;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 4px 10px;
}
QPushButton[compact="true"]:hover {
    background: #334155;
}
QPushButton[variant="secondary"] {
    background: #1F2937;
    color: #E5E7EB;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 8px 14px;
}
QPushButton[variant="secondary"]:hover {
    background: #334155;
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
QTableWidget {
    background: #0B1220;
    border: 1px solid #1F2937;
    border-radius: 12px;
    gridline-color: #1F2937;
    color: #E5E7EB;
    selection-background-color: #1D4ED8;
    selection-color: #F8FAFC;
    alternate-background-color: #0F1B2D;
}
QTableWidget::item {
    background: #0B1220;
    color: #E5E7EB;
    padding: 4px;
}
QTableWidget::item:alternate {
    background: #0F1B2D;
    color: #E5E7EB;
}
QTableWidget::item:selected {
    background: #1D4ED8;
    color: #F8FAFC;
}
QAbstractItemView {
    selection-background-color: #1D4ED8;
    selection-color: #F8FAFC;
}
QComboBox QAbstractItemView {
    background: #0B1220;
    color: #E5E7EB;
    border: 1px solid #1F2937;
    selection-background-color: #1D4ED8;
    selection-color: #F8FAFC;
}
QProgressBar {
    background: #0B1220;
    border: 1px solid #1F2937;
    border-radius: 8px;
    text-align: center;
    color: #E5E7EB;
}
QProgressBar::chunk {
    background: #2563EB;
    border-radius: 8px;
}
QLabel[textRole="muted"] {
    color: #94A3B8;
}
QLabel[textRole="muted"][size="small"] {
    color: #94A3B8;
    font-size: 11px;
}
QLabel[textRole="danger"] {
    color: #F87171;
}
QLabel[textRole="danger"][size="small"] {
    color: #F87171;
    font-size: 11px;
}
QDialog#LockDialog {
    background: rgba(2, 6, 23, 0.65);
}
QFrame#LockCard {
    background: #111827;
    border-radius: 16px;
    padding: 8px;
    min-width: 320px;
    border: 1px solid #1F2937;
}
QLabel#LockTitle {
    color: #F8FAFC;
    font-size: 18px;
    font-weight: 700;
}
QLabel#LockHint {
    color: #94A3B8;
    font-size: 12px;
}
QLabel#LockError {
    color: #F87171;
    font-size: 12px;
}
QToolTip {
    background: #111827;
    color: #F9FAFB;
    border: 1px solid #1F2937;
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
