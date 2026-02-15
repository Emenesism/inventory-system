from __future__ import annotations

import faulthandler
import logging
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, Qt, QTranslator
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
from PySide6.QtWidgets import QApplication

_CRASH_FILE = None

if __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import AppConfig
from app.core.logging_setup import setup_logging
from app.data.inventory_store import InventoryStore
from app.services.inventory_service import InventoryService
from app.ui.fonts import resolve_ui_font_stack
from app.ui.main_window import MainWindow


def main() -> int:
    setup_logging()
    _install_exception_hook()
    _install_crash_logging()
    _install_thread_exception_hook()
    _install_unraisable_hook()
    _configure_high_dpi()
    app = QApplication(sys.argv)
    _install_localization(app)
    app.setStyle("Fusion")
    _install_qt_message_handler()
    _log_app_lifecycle(app)

    config = AppConfig.load()
    store = InventoryStore()
    inventory_service = InventoryService(store, config)

    window = MainWindow(inventory_service, config)
    window.show()
    return app.exec()


def _install_localization(app: QApplication) -> None:
    locale = QLocale("fa_IR")
    QLocale.setDefault(locale)
    app.setLayoutDirection(Qt.RightToLeft)
    _apply_persian_font(app)

    translators: list[QTranslator] = []
    qt_translator = QTranslator(app)
    if qt_translator.load(
        locale,
        "qtbase",
        "_",
        QLibraryInfo.path(QLibraryInfo.TranslationsPath),
    ):
        app.installTranslator(qt_translator)
        translators.append(qt_translator)

    app_translator = QTranslator(app)
    qm_path = Path(__file__).resolve().parent / "i18n" / "fa_IR.qm"
    if app_translator.load(str(qm_path)):
        app.installTranslator(app_translator)
        translators.append(app_translator)

    # Keep explicit references to avoid garbage collection in some bindings.
    app._translators = translators  # type: ignore[attr-defined]


def _apply_persian_font(app: QApplication) -> None:
    font_stack = resolve_ui_font_stack(QFontDatabase.families(), limit=4)
    app.setProperty("ui_font_stack", font_stack)
    primary_family = font_stack[0] if font_stack else ""
    if not primary_family:
        return
    font = QFont(primary_family)
    font.setPointSize(10)
    app.setFont(font)


def _configure_high_dpi() -> None:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:  # noqa: BLE001
        pass


def _install_exception_hook() -> None:
    logger = logging.getLogger("UnhandledException")

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        logger.exception(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception


def _install_crash_logging() -> None:
    try:
        from app.core.logging_setup import LOG_DIR

        crash_path = LOG_DIR / "crash.log"
        crash_path.parent.mkdir(parents=True, exist_ok=True)
        global _CRASH_FILE
        _CRASH_FILE = open(crash_path, "a", encoding="utf-8", buffering=1)
        faulthandler.enable(file=_CRASH_FILE, all_threads=True)
        logger = logging.getLogger("CrashLogger")
        logger.info("Crash logging enabled at %s", crash_path)
    except Exception:  # noqa: BLE001
        logging.getLogger("CrashLogger").exception(
            "Failed to enable crash logging"
        )


def _install_qt_message_handler() -> None:
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        qt_logger = logging.getLogger("Qt")

        def handle_qt_message(mode, context, message) -> None:  # noqa: ANN001
            if mode == QtMsgType.QtDebugMsg:
                qt_logger.debug(message)
            elif mode == QtMsgType.QtInfoMsg:
                qt_logger.info(message)
            elif mode == QtMsgType.QtWarningMsg:
                qt_logger.warning(message)
            elif mode == QtMsgType.QtCriticalMsg:
                qt_logger.error(message)
            elif mode == QtMsgType.QtFatalMsg:
                qt_logger.critical(message)
            else:
                qt_logger.info(message)

        qInstallMessageHandler(handle_qt_message)
    except Exception:  # noqa: BLE001
        logging.getLogger("Qt").exception(
            "Failed to install Qt message handler"
        )


def _install_thread_exception_hook() -> None:
    logger = logging.getLogger("ThreadException")

    def handle(args: threading.ExceptHookArgs) -> None:
        logger.exception(
            "Unhandled thread exception",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = handle


def _install_unraisable_hook() -> None:
    logger = logging.getLogger("UnraisableException")

    def handle(unraisable) -> None:  # noqa: ANN001
        logger.error(
            "Unraisable exception",
            exc_info=(
                unraisable.exc_type,
                unraisable.exc_value,
                unraisable.exc_traceback,
            ),
        )

    sys.unraisablehook = handle


def _log_app_lifecycle(app: QApplication) -> None:
    logger = logging.getLogger("AppLifecycle")
    app.aboutToQuit.connect(lambda: logger.warning("Application about to quit"))


if __name__ == "__main__":
    raise SystemExit(main())
