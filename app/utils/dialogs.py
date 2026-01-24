from PySide6.QtWidgets import QMessageBox, QWidget


def show_error(parent: QWidget, title: str, message: str) -> None:
    QMessageBox.critical(parent, title, message)


def show_info(parent: QWidget, title: str, message: str) -> None:
    QMessageBox.information(parent, title, message)


def ask_yes_no(parent: QWidget, title: str, message: str) -> bool:
    result = QMessageBox.question(parent, title, message, QMessageBox.Yes | QMessageBox.No)
    return result == QMessageBox.Yes
