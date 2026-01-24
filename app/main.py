from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

if __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import AppConfig
from app.core.logging_setup import setup_logging
from app.data.inventory_store import InventoryStore
from app.services.inventory_service import InventoryService
from app.ui.main_window import MainWindow


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    config = AppConfig.load()
    store = InventoryStore()
    inventory_service = InventoryService(store, config)

    window = MainWindow(inventory_service, config)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
