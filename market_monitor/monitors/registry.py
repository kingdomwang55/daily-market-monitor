"""Monitor 注册表。

保持注册表轻量：列出 monitor 不应导入所有运行时依赖。
"""
from dataclasses import dataclass
from importlib import import_module


@dataclass(frozen=True)
class MonitorSpec:
    name: str
    display: str
    module: str
    class_name: str


REGISTRY = {
    spec.name: spec
    for spec in [
        MonitorSpec("stabilize", "企稳信号", ".stabilize", "StabilizeMonitor"),
        MonitorSpec("us_market", "美股夜盘", ".us_market", "UsMarketMonitor"),
        MonitorSpec("hk_market", "港股监控", ".hk_market", "HkMarketMonitor"),
        MonitorSpec("shock", "A股异动", ".shock", "ShockMonitor"),
        MonitorSpec("hk_shock", "港股异动", ".hk_shock", "HkShockMonitor"),
        MonitorSpec("price_alert", "关键点位", ".price_alert", "PriceAlertMonitor"),
        MonitorSpec("morning", "晨间报告", ".morning", "MorningMonitor"),
        MonitorSpec("evening", "盘后报告", ".evening", "EveningMonitor"),
        MonitorSpec("voice", "意见领袖", ".voice_monitor", "VoiceMonitor"),
        MonitorSpec("macro", "宏观监控", ".macro_monitor", "MacroMonitor"),
        MonitorSpec("review", "周度复盘", ".review", "ReviewMonitor"),
        MonitorSpec("monthly", "月度复盘", ".monthly", "MonthlyMonitor"),
        MonitorSpec("midday", "午间综述", ".midday", "MiddayMonitor"),
        MonitorSpec("pulse", "盘中脉搏", ".pulse", "PulseMonitor"),
        MonitorSpec("shanghai_watch", "上证 3800 剧本", ".shanghai_watch", "ShanghaiWatchMonitor"),
    ]
}


def get_monitor(name: str):
    """获取 monitor 类，按需导入对应模块。"""
    spec = REGISTRY.get(name)
    if spec is None:
        raise KeyError(
            f"未知的 monitor: {name}\n"
            f"可用: {', '.join(REGISTRY.keys())}"
        )
    module = import_module(spec.module, package=__package__)
    return getattr(module, spec.class_name)


def list_monitors():
    """列出所有 monitor，不触发运行时依赖导入。"""
    return [
        {"name": name, "display": spec.display}
        for name, spec in REGISTRY.items()
    ]
