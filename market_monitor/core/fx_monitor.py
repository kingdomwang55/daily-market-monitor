"""外汇扩展监控（Extended FX Monitor）

在原有美元指数（DXY）之上，扩展 3 大关键汇率：
1. USD/JPY —— 日元套息交易/日央干预风向标
2. USD/CNH —— 离岸人民币，A/港股外资流出压力信号
3. EUR/USD —— 欧元区风险偏好

数据源：Yahoo Finance
更新粒度：跟随晨报/盘后（低频，仅日频数据）

暴露接口：
- fetch_all() → 返回 dict[name → {price, pct, prev_close}]
- format_fx_block() → 生成报告文本区块
- get_fx_signals() → 关键异动信号（供 cross_asset 使用）
"""
from typing import Dict, List, Optional

from . import data_source as ds


# ── 关键汇率符号 ────────────────────────────────────────────
FX_SYMBOLS = [
    ("USDJPY=X", "USD/JPY", "日元"),
    ("CNH=X",    "USD/CNH", "离岸人民币"),
    ("EURUSD=X", "EUR/USD", "欧元"),
]

# 关键阈值（触发预警）
# USD/CNH: 数值越高 = 人民币越弱
# 当前区间约 6.7-7.3，阈值按实际 meaningful levels 设
FX_ALERT_THRESHOLDS = {
    "USD/JPY": {
        "level_upper": 160.0,   # 突破 160 = 日央可能干预
        "daily_change_pct": 1.0,  # 单日变动 1% 视为剧烈
    },
    "USD/CNH": {
        "level_upper": 7.30,    # 破 7.30 = 央行心理关口（人民币大幅贬值）
        "level_upper_warn": 7.15,  # 接近 7.15 = 贬值压力上升
        "daily_change_pct": 0.5,
    },
    "EUR/USD": {
        "daily_change_pct": 0.8,
    },
}


def fetch_all() -> Dict[str, Dict]:
    """拉取所有关键汇率"""
    result = {}
    for symbol, name, _label in FX_SYMBOLS:
        try:
            q = ds.yahoo_quote(symbol)
            if q:
                result[name] = q
        except Exception as e:
            print(f"[fx_monitor] {name} 拉取失败: {e}")
    return result


def format_fx_block(fx_data: Dict[str, Dict], compact: bool = False) -> str:
    """生成外汇区块文本"""
    if not fx_data:
        return ""

    lines = ["【外汇（USD 计价）】" if not compact else "【FX】"]
    for symbol, name, label in FX_SYMBOLS:
        q = fx_data.get(name)
        if not q:
            lines.append(f"  {label:8s}: -")
            continue
        price = q.get("price") or q.get("close", 0)
        pct = q.get("pct", 0)
        # USD/JPY 用 2 位小数，其他用 4 位
        if name == "USD/JPY":
            price_str = f"{price:>10.2f}"
        else:
            price_str = f"{price:>10.4f}"
        # 附加信号 tag
        tag = ""
        thr = FX_ALERT_THRESHOLDS.get(name, {})
        if thr.get("level_upper") and price >= thr["level_upper"]:
            tag = " ⚠️破上关口"
        elif thr.get("level_upper_warn") and price >= thr["level_upper_warn"]:
            tag = " ⚠️接近关口"
        elif thr.get("daily_change_pct") and abs(pct) >= thr["daily_change_pct"]:
            tag = f" {'📈' if pct > 0 else '📉'}剧烈波动"
        lines.append(f"  {label:8s}: {price_str} ({pct:+.2f}%){tag}")

    return "\n".join(lines)


def get_fx_signals(fx_data: Dict[str, Dict]) -> List[Dict]:
    """把外汇异动转成 cross_asset 可用的信号

    返回信号列表：
    [{"name": "USD/JPY 突破 160", "narrative": ..., "severity": "high"}, ...]
    """
    signals = []

    # 1. 日元 —— 干预警报
    jpy = fx_data.get("USD/JPY")
    if jpy:
        price = jpy.get("price") or jpy.get("close", 0)
        pct = jpy.get("pct", 0)
        if price >= 160:
            signals.append({
                "name": "日元贬破 160 · 干预风险",
                "severity": "high",
                "narrative": (
                    f"USD/JPY 触及 {price:.2f}，逼近或突破日央干预区间\n"
                    "  ↓ 传导：一旦干预 → 美债抛售 → 全球利率联动上行 → 成长股承压"
                ),
                "affected": ["纳斯达克", "创业板指", "沪金主力"],
            })
        elif pct <= -1.5:
            # 日元大幅走强，可能刚干预完
            signals.append({
                "name": "日元急剧走强",
                "severity": "medium",
                "narrative": (
                    f"USD/JPY 单日下跌 {pct:.2f}%，日元套息交易可能被强制平仓\n"
                    "  ↓ 传导：全球风险资产波动加剧，A/港股情绪转弱"
                ),
                "affected": ["恒生指数", "上证指数"],
            })

    # 2. 离岸人民币 —— A/港股外资流出压力
    cnh = fx_data.get("USD/CNH")
    if cnh:
        price = cnh.get("price") or cnh.get("close", 0)
        pct = cnh.get("pct", 0)
        if price >= 7.30:
            signals.append({
                "name": "人民币破 7.30 · 外资流出压力",
                "severity": "high",
                "narrative": (
                    f"USD/CNH 达 {price:.4f}，突破 7.30 心理关口\n"
                    "  ↓ 传导：外资从 A 股/港股撤离压力显著上升，"
                    "港股承压更甚（联汇制关联），大消费/金融板块承压"
                ),
                "affected": ["上证指数", "恒生指数"],
            })
        elif pct >= 0.5:
            signals.append({
                "name": "人民币显著贬值",
                "severity": "medium",
                "narrative": (
                    f"USD/CNH 单日上涨 {pct:.2f}%，人民币贬值压力上升\n"
                    "  ↓ 传导：外资流出压力，A/港股承压；出口链条相对受益"
                ),
                "affected": ["上证指数", "恒生指数"],
            })

    return signals
