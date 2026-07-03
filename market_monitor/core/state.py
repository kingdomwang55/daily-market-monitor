"""状态管理"""
import json
from pathlib import Path

from .config import get_config


class State:
    """基于 JSON 文件的状态存储，用于防止重复提醒"""

    def __init__(self, name: str):
        cfg = get_config()
        self.path = Path(cfg.state_dir) / f"{name}_state.json"
        self._data = self._load()

    def _load(self) -> dict:
        try:
            with open(self.path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value=True):
        self._data[key] = value

    def has(self, key: str) -> bool:
        return key in self._data and bool(self._data[key])

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w") as f:
                json.dump(self._data, f, ensure_ascii=False)
        except Exception:
            pass

    def clear(self):
        self._data = {}
        self.save()
