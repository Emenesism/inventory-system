import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.json"


@dataclass
class AppConfig:
    inventory_file: str | None = None
    theme: str = "light"
    low_stock_threshold: int = 5

    @classmethod
    def load(cls) -> "AppConfig":
        if not CONFIG_PATH.exists():
            return cls()
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        return cls(
            inventory_file=data.get("inventory_file"),
            theme=data.get("theme", "light"),
            low_stock_threshold=data.get("low_stock_threshold", 5),
        )

    def save(self) -> None:
        data = {
            "inventory_file": self.inventory_file,
            "theme": self.theme,
            "low_stock_threshold": self.low_stock_threshold,
        }
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
