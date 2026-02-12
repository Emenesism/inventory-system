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
    backend_url: str = "http://127.0.0.1:8080"
    theme: str = "light"
    low_stock_threshold: int = 5
    access_token: str | None = None

    @classmethod
    def _default_data(cls) -> dict[str, str | int | None]:
        return {
            "inventory_file": None,
            "backend_url": "http://127.0.0.1:8080",
            "theme": "light",
            "low_stock_threshold": 5,
            "access_token": None,
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
            backend_url=str(data.get("backend_url", "http://127.0.0.1:8080")),
            theme=data.get("theme", "light"),
            low_stock_threshold=data.get("low_stock_threshold", 5),
            access_token=data.get("access_token"),
        )

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "inventory_file": self.inventory_file,
            "backend_url": self.backend_url,
            "theme": self.theme,
            "low_stock_threshold": self.low_stock_threshold,
            "access_token": self.access_token,
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
                backend_url=str(
                    data.get("backend_url", "http://127.0.0.1:8080")
                ),
                theme=data.get("theme", "light"),
                low_stock_threshold=data.get("low_stock_threshold", 5),
                access_token=data.get("access_token"),
            )
