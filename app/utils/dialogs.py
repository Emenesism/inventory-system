import logging

from PySide6.QtWidgets import QMessageBox, QWidget

logger = logging.getLogger(__name__)


def show_error(parent: QWidget, title: str, message: str) -> None:
    logger.error("%s: %s", title, message)
    QMessageBox.critical(parent, title, message)


def show_info(parent: QWidget, title: str, message: str) -> None:
    logger.info("%s: %s", title, message)
    QMessageBox.information(parent, title, message)


def ask_yes_no(parent: QWidget, title: str, message: str) -> bool:
    logger.info("%s: %s", title, message)
    result = QMessageBox.question(
        parent, title, message, QMessageBox.Yes | QMessageBox.No
    )
    return result == QMessageBox.Yes
