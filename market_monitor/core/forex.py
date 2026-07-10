"""外汇监控扩展（Forex Extension）

P1-1：在现有美元指数基础上扩展 JPY/CNH 交叉汇率监控。
Yahoo Finance 数据源，与 data_source.yahoo_quote 同源。

核心功能：
- fetch_forex() → 拉取 USDJPY / USDCNH / EURUSD / GBPUSD 等
- format_forex() → 格式化文本（报告用）
- forex_summary_for_ai() → 紧凑版（AI prompt 用）
- analyze_forex_signals() → 外汇异动信号检测
"""
from typing import Dict, List, Optional
from . import data_source as ds


# 监控的外汇对
FOREX_PAIRS = [
    ("USDCNH=X", "美元离岸人民币", "🇨🇳"),
    ("USDJPY=X", "美元日元", "🇯🇵"),
    ("EURUSD=X", "欧元美元", "🇪🇺"),
    ("GBPUSD=X", "英镑美元", "🇬🇧"),
]

# 信号阈值
SIGNIFICANT_PCT = {
    "美元离岸人民币": 0.3,   # CNH 波动较小
    "美元日元": 0.5,         # JPY 波动较大
    "欧元美元": 0.3,
    "英镑美元": 0.3,
}


def fetch_forex() -> Dict[str, dict]:
    """拉取所有外汇对数据

    Returns:
        {name: {price, prev, pct, change_pct, pair}, ...}
    """
    result = {}
    for symbol, name, flag in FOREX_PAIRS:
        q = ds.yahoo_quote(symbol)
        if q:
            q["pair"] = symbol
            q["flag"] = flag
            result[name] = q
    return result


def format_forex(forex_data: Dict[str, dict]) -> str:
    """格式化为报告文本"""
    if not forex_data:
        return ""
    lines = ["【外汇】"]
    for name, q in forex_data.items():
        flag = q.get("flag", "")
        price = q.get("price", 0)
        pct = q.get("pct", 0)
        lines.append(f"  {flag} {name:8s}: {price:>10.4f} ({pct:+.2f}%)")
    return "\n".join(lines)


def forex_summary_for_ai(forex_data: Dict[str, dict]) -> str:
    """给 AI 看的紧凑版"""
    if not forex_data:
        return "外汇：无数据"
    parts = ["外汇市场："]
    for name, q in forex_data.items():
        price = q.get("price", 0)
        pct = q.get("pct", 0)
        parts.append(f"- {name}: {price:.4f} ({pct:+.2f}%)")
    return "\n".join(parts)


def analyze_forex_signals(forex_data: Dict[str, dict]) -> List[Dict]:
    """检测外汇异动信号

    Returns:
        [{name, direction, pct, narrative, affected}, ...]
    """
    signals = []
    for name, q in forex_data.items():
        pct = q.get("pct", 0)
        threshold = SIGNIFICANT_PCT.get(name, 0.3)
        if abs(pct) < threshold:
            continue

        direction = "升值" if pct > 0 else "贬值"
        # 判断对 A 股/港股的影响
        if name == "美元离岸人民币":
            if pct > 0:
                # CNH 贬值（美元涨）
                narrative = f"离岸人民币贬值 ({pct:+.2f}%) → 外资流出压力上升，A股承压"
                affected = ["上证指数", "恒生指数"]
                severity = "high" if pct > 0.5 else "medium"
            else:
                narrative = f"离岸人民币升值 ({pct:+.2f}%) → 外资流入预期，A股利好"
                affected = ["上证指数", "恒生指数"]
                severity = "medium"
        elif name == "美元日元":
            if pct > 0:
                narrative = f"日元贬值 ({pct:+.2f}%) → 可能有干预风险，亚洲货币承压"
                affected = ["上证指数", "恒生指数"]
                severity = "medium"
            else:
                narrative = f"日元升值 ({pct:+.2f}%) → 避险情绪升温，日股资金可能外溢"
                affected = ["纳斯达克"]
                severity = "low"
        elif name == "欧元美元":
            if pct < 0:
                narrative = f"欧元走弱 ({pct:+.2f}%) → 美元被动走强，新兴市场承压"
                affected = ["上证指数"]
                severity = "low"
            else:
                narrative = f"欧元走强 ({pct:+.2f}%) → 美元走弱，风险资产受益"
                affected = ["纳斯达克"]
                severity = "low"
        else:
            narrative = f"{name}波动 {pct:+.2f}%"
            affected = []
            severity = "low"

        signals.append({
            "name": name,
            "direction": direction,
            "pct": round(pct, 2),
            "narrative": narrative,
            "affected": affected,
            "severity": severity,
        })
    return signals
