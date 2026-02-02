from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from app.core.config import AppConfig
from app.data.inventory_store import InventoryStore
from app.models.errors import InventoryFileError
from app.services.backup_sender import send_backup
from app.utils.text import normalize_text


class InventoryService:
    def __init__(self, store: InventoryStore, config: AppConfig) -> None:
        self.store = store
        self.config = config
        self._name_index: dict[str, int] = {}
        self._logger = logging.getLogger(self.__class__.__name__)
        self._sync_passphrase()

    def set_inventory_path(self, path: str | Path | None) -> None:
        self.store.set_path(path)
        self.config.inventory_file = str(path) if path else None
        self.config.save()

    def load(self) -> pd.DataFrame:
        self._sync_passphrase()
        df = self.store.load()
        self._rebuild_index(df)
        return df

    def save(
        self, df: pd.DataFrame, admin_username: str | None = None
    ) -> Path | None:
        self._sync_passphrase()
        backup_dir = (
            Path(self.config.backup_dir) if self.config.backup_dir else None
        )
        backup_path = self.store.backup(backup_dir=backup_dir)
        self.store.save(df)
        self._rebuild_index(df)
        send_backup(
            reason="inventory_saved",
            config=self.config,
            admin_username=admin_username,
        )
        if backup_path:
            self._logger.info(
                "Inventory saved. Backup created at %s", backup_path
            )
        else:
            self._logger.info("Inventory saved. No backup was created.")
        return backup_path

    def get_dataframe(self) -> pd.DataFrame:
        if self.store.dataframe is None:
            raise InventoryFileError("Inventory not loaded.")
        return self.store.dataframe

    def is_loaded(self) -> bool:
        return self.store.dataframe is not None

    def get_product_names(self) -> list[str]:
        if not self.is_loaded():
            return []
        df = self.store.dataframe
        return df["product_name"].astype(str).str.strip().tolist()

    def find_index(self, product_name: str) -> int | None:
        key = self._normalize_name(product_name)
        return self._name_index.get(key)

    def _rebuild_index(self, df: pd.DataFrame) -> None:
        self._name_index = {
            self._normalize_name(name): idx
            for idx, name in df["product_name"].items()
        }

    @staticmethod
    def _normalize_name(name: str) -> str:
        return normalize_text(name)

    def _sync_passphrase(self) -> None:
        passphrase = self.config.inventory_key or self.config.passcode
        self.store.set_passphrase(passphrase)
