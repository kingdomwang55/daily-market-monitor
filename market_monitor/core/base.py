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
        self.last_push_log_id = None

    @property
    def now_str(self) -> str:
        return self.now.strftime("%Y-%m-%d %H:%M")

    @property
    def today(self) -> str:
        return self.now.strftime("%Y-%m-%d")

    def log(self, msg: str):
        print(f"[{self.name}] {msg}", file=sys.stderr)

    def send(self, message: str, meta: Optional[dict] = None) -> bool:
        ok = send_text(message, push_type=self.name, meta=meta)
        # 新增：推送自动落库（Phase 1 核心）
        self.last_push_log_id = self._log_push(message, meta, ok)
        return ok

    # ==================================================
    # 数据层：推送/信号落库（失败不会卡住推送）
    # ==================================================
    def _log_push(self, message: str, meta: Optional[dict],
                  sent_ok: bool) -> Optional[int]:
        """将推送写入 push_log 表，返回 push_log.id"""
        try:
            from ..data.database import get_session
            from ..data.repositories import PushLogRepository, SignalEventRepository
        except Exception:
            return None

        try:
            m = meta or {}
            with get_session() as s:
                row = PushLogRepository(s).create(
                    monitor=self.name,
                    message=message,
                    scenario=m.get("scenario"),
                    max_level=int(m.get("max_level", 0)),
                    title=m.get("title") or self.display_name,
                    context=m,
                    sent_ok=sent_ok,
                )
                # 可选：记录 signal_event
                signal_type = m.get("signal_type")
                if signal_type:
                    SignalEventRepository(s).create(
                        monitor=self.name,
                        signal_type=signal_type,
                        symbol=m.get("symbol"),
                        level=int(m.get("max_level", 0)),
                        hk_avg_pct=m.get("hk_avg_pct"),
                        a_avg_pct=m.get("a_avg_pct"),
                        metrics=m.get("metrics"),
                        push_log_id=row.id,
                    )
                return row.id
        except Exception as e:
            # 落库失败不影响推送主流程
            print(f"[{self.name}] 落库失败（不影响推送）: {e}", file=sys.stderr)
            return None

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
