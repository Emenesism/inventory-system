import json
import threading
from dataclasses import dataclass
from pathlib import Path

from app.core.paths import app_dir

CONFIG_PATH = app_dir() / "config.json"
_CONFIG_LOCK = threading.RLock()


@dataclass
class AppConfig:
    inventory_file: str | None = None
    theme: str = "light"
    low_stock_threshold: int = 5
    backup_dir: str | None = None
    passcode: str = "1111"
    inventory_key: str | None = None
    access_token: str | None = None
    bot_token: str | None = None
    bot_token_for_sending: str | None = None
    channel_id: str | None = None
    bale_last_backup_name: str | None = None

    @classmethod
    def _default_data(cls) -> dict[str, str | int | None]:
        return {
            "inventory_file": None,
            "theme": "light",
            "low_stock_threshold": 5,
            "backup_dir": None,
            "passcode": "1111",
            "inventory_key": None,
            "access_token": None,
            "bot_token": None,
            "bot_token_for_sending": None,
            "channel_id": None,
            "bale_last_backup_name": None,
        }

    @classmethod
    def _read_data_locked(cls) -> dict[str, str | int | None]:
        if not CONFIG_PATH.exists():
            return cls._default_data()
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls._default_data()
        if not isinstance(raw, dict):
            return cls._default_data()
        data = cls._default_data()
        for key in data:
            if key in raw:
                data[key] = raw.get(key)
        return data

    @classmethod
    def _write_data_locked(cls, data: dict[str, str | int | None]) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = CONFIG_PATH.with_name(f"{CONFIG_PATH.name}.tmp")
        tmp_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp_path.replace(CONFIG_PATH)

    @classmethod
    def load(cls) -> "AppConfig":
        with _CONFIG_LOCK:
            data = cls._read_data_locked()
        return cls(
            inventory_file=data.get("inventory_file"),
            theme=data.get("theme", "light"),
            low_stock_threshold=data.get("low_stock_threshold", 5),
            backup_dir=data.get("backup_dir"),
            passcode=str(data.get("passcode", "1111")),
            inventory_key=data.get("inventory_key"),
            access_token=data.get("access_token"),
            bot_token=data.get("bot_token"),
            bot_token_for_sending=data.get("bot_token_for_sending"),
            channel_id=data.get("channel_id"),
            bale_last_backup_name=data.get("bale_last_backup_name"),
        )

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "inventory_file": self.inventory_file,
            "theme": self.theme,
            "low_stock_threshold": self.low_stock_threshold,
            "backup_dir": self.backup_dir,
            "passcode": self.passcode,
            "inventory_key": self.inventory_key,
            "access_token": self.access_token,
            "bot_token": self.bot_token,
            "bot_token_for_sending": self.bot_token_for_sending,
            "channel_id": self.channel_id,
            "bale_last_backup_name": self.bale_last_backup_name,
        }

    def save(self) -> None:
        with _CONFIG_LOCK:
            self._write_data_locked(self.to_dict())

    @classmethod
    def save_partial(cls, **updates) -> "AppConfig":
        with _CONFIG_LOCK:
            data = cls._read_data_locked()
            for key, value in updates.items():
                if key in data:
                    data[key] = value
            cls._write_data_locked(data)
            return cls(
                inventory_file=data.get("inventory_file"),
                theme=data.get("theme", "light"),
                low_stock_threshold=data.get("low_stock_threshold", 5),
                backup_dir=data.get("backup_dir"),
                passcode=str(data.get("passcode", "1111")),
                inventory_key=data.get("inventory_key"),
                access_token=data.get("access_token"),
                bot_token=data.get("bot_token"),
                bot_token_for_sending=data.get("bot_token_for_sending"),
                channel_id=data.get("channel_id"),
                bale_last_backup_name=data.get("bale_last_backup_name"),
            )
