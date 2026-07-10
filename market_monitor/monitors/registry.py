"""Monitor 注册表"""
from .stabilize import StabilizeMonitor
from .us_market import UsMarketMonitor
from .hk_market import HkMarketMonitor
from .shock import ShockMonitor
from .hk_shock import HkShockMonitor
from .price_alert import PriceAlertMonitor
from .morning import MorningMonitor
from .evening import EveningMonitor
from .voice_monitor import VoiceMonitor
from .macro_monitor import MacroMonitor
from .review import ReviewMonitor
from .monthly import MonthlyMonitor
from .midday import MiddayMonitor
from .pulse import PulseMonitor

REGISTRY = {
    m.name: m for m in [
        StabilizeMonitor,
        UsMarketMonitor,
        HkMarketMonitor,
        ShockMonitor,
        HkShockMonitor,
        PriceAlertMonitor,
        MorningMonitor,
        EveningMonitor,
        VoiceMonitor,
        MacroMonitor,
        ReviewMonitor,
        MonthlyMonitor,
        MiddayMonitor,
        PulseMonitor,
    ]
}


def get_monitor(name: str):
    """获取 monitor 类"""
    if name not in REGISTRY:
        raise KeyError(
            f"未知的 monitor: {name}\n"
            f"可用: {', '.join(REGISTRY.keys())}"
        )
    return REGISTRY[name]


def list_monitors():
    """列出所有 monitor"""
    return [
        {"name": name, "display": cls.display_name}
        for name, cls in REGISTRY.items()
    ]
