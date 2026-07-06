"""Monitor 基类"""
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from .config import get_config
from .state import State
from .feishu import send_text


class BaseMonitor(ABC):
    """所有监控继承此基类"""

    #: 唯一标识（用于 CLI / state 文件名）
    name: str = ""
    #: 展示名
    display_name: str = ""

    def __init__(self, force: bool = False, snapshot: bool = False):
        self.config = get_config()
        self.state = State(self.name)
        self.force = force
        self.snapshot = snapshot
        self.now = datetime.now()

    @property
    def now_str(self) -> str:
        return self.now.strftime("%Y-%m-%d %H:%M")

    @property
    def today(self) -> str:
        return self.now.strftime("%Y-%m-%d")

    def log(self, msg: str):
        print(f"[{self.name}] {msg}", file=sys.stderr)

    def send(self, message: str, meta: Optional[dict] = None) -> bool:
        return send_text(message, push_type=self.name, meta=meta)

    @staticmethod
    def emoji_by_pct(pct: float) -> str:
        if pct >= 2:
            return "🚀"
        if pct >= 0.5:
            return "🟢"
        if pct <= -2:
            return "💥"
        if pct <= -0.5:
            return "🔴"
        return "⚪"

    @abstractmethod
    def run(self) -> bool:
        """执行监控。返回 True 表示成功（无论是否推送）"""
        raise NotImplementedError
