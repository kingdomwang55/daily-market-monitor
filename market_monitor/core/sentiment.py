"""市场情绪指标（Sentiment Indicators）

P1-3：整合 VIX（已有）+ SKEW + Put/Call Ratio + Fear & Greed Index 的替代
数据源：Yahoo Finance（^VIX, ^SKEW, ^VVIX）

核心功能：
- fetch_sentiment() → 拉取情绪指标
- interpret_vix() → VIX 水平解读（<15 平静 / 15-20 正常 / 20-30 紧张 / >30 恐慌）
- interpret_skew() → SKEW 解读（>150 尾部风险担忧）
- format_sentiment() → 报告文本
- sentiment_summary_for_ai() → AI 用紧凑版
- analyze_sentiment_signals() → 情绪极端信号
"""
from typing import Dict, List, Optional
from . import data_source as ds


# 情绪指标符号
SENTIMENT_SYMBOLS = [
    ("^VIX", "VIX", "恐慌指数"),
    ("^SKEW", "SKEW", "尾部风险指数"),
    ("^VVIX", "VVIX", "VIX的波动率"),
]


def fetch_sentiment() -> Dict[str, dict]:
    """拉取所有情绪指标

    Returns:
        {name: {price, prev, pct, desc}, ...}
    """
    result = {}
    for symbol, name, desc in SENTIMENT_SYMBOLS:
        q = ds.yahoo_quote(symbol)
        if q:
            q["desc"] = desc
            q["symbol"] = symbol
            result[name] = q
    return result


def interpret_vix(vix_price: float) -> Dict[str, str]:
    """VIX 水平解读"""
    if vix_price < 15:
        return {"level": "平静", "emoji": "😴", "meaning": "市场平静，可能有盲目乐观风险"}
    elif vix_price < 20:
        return {"level": "正常", "emoji": "😐", "meaning": "正常波动区间"}
    elif vix_price < 30:
        return {"level": "紧张", "emoji": "😰", "meaning": "市场紧张，波动加剧"}
    elif vix_price < 40:
        return {"level": "恐慌", "emoji": "😱", "meaning": "恐慌情绪显著"}
    else:
        return {"level": "极度恐慌", "emoji": "💀", "meaning": "极端恐慌，历史上多为底部区间"}


def interpret_skew(skew_price: float) -> Dict[str, str]:
    """SKEW 解读（历史范围 100-170）
    
    SKEW > 150 表示市场担忧尾部风险（黑天鹅事件概率上升）
    SKEW < 120 表示市场对尾部风险不担忧
    """
    if skew_price < 120:
        return {"level": "低尾部风险", "emoji": "🟢", "meaning": "市场对尾部风险不担忧"}
    elif skew_price < 140:
        return {"level": "正常", "emoji": "🟡", "meaning": "正常水平"}
    elif skew_price < 150:
        return {"level": "尾部风险抬升", "emoji": "🟠", "meaning": "对冲基金开始买入尾部保护"}
    else:
        return {"level": "尾部风险显著", "emoji": "🔴", "meaning": "市场担忧黑天鹅事件，配置尾部保护"}


def format_sentiment(sentiment: Dict[str, dict]) -> str:
    """格式化为报告文本"""
    if not sentiment:
        return ""
    lines = ["【市场情绪】"]

    vix = sentiment.get("VIX")
    if vix:
        interp = interpret_vix(vix["price"])
        lines.append(f"  {interp['emoji']} VIX     : {vix['price']:>6.2f} ({vix['pct']:+.2f}%) [{interp['level']}]")

    skew = sentiment.get("SKEW")
    if skew:
        interp = interpret_skew(skew["price"])
        lines.append(f"  {interp['emoji']} SKEW    : {skew['price']:>6.2f} ({skew['pct']:+.2f}%) [{interp['level']}]")

    vvix = sentiment.get("VVIX")
    if vvix:
        lines.append(f"  📊 VVIX    : {vvix['price']:>6.2f} ({vvix['pct']:+.2f}%)")

    return "\n".join(lines)


def sentiment_summary_for_ai(sentiment: Dict[str, dict]) -> str:
    """给 AI 看的紧凑版"""
    if not sentiment:
        return "情绪指标：无数据"
    parts = ["市场情绪指标："]

    vix = sentiment.get("VIX")
    if vix:
        interp = interpret_vix(vix["price"])
        parts.append(f"- VIX(恐慌指数): {vix['price']:.2f} ({vix['pct']:+.2f}%) → {interp['level']}: {interp['meaning']}")

    skew = sentiment.get("SKEW")
    if skew:
        interp = interpret_skew(skew["price"])
        parts.append(f"- SKEW(尾部风险): {skew['price']:.2f} ({skew['pct']:+.2f}%) → {interp['level']}: {interp['meaning']}")

    vvix = sentiment.get("VVIX")
    if vvix:
        parts.append(f"- VVIX(VIX 的波动率): {vvix['price']:.2f} ({vvix['pct']:+.2f}%)")

    return "\n".join(parts)


def analyze_sentiment_signals(sentiment: Dict[str, dict]) -> List[Dict]:
    """情绪极端信号检测"""
    signals = []

    vix = sentiment.get("VIX")
    if vix:
        vix_price = vix["price"]
        vix_pct = vix.get("pct", 0)

        if vix_price >= 30:
            signals.append({
                "name": "VIX 极端恐慌",
                "narrative": (
                    f"VIX = {vix_price:.2f}（>30） → 市场恐慌\n"
                    "  ↓ 历史上极端恐慌区间多为反弹或底部信号\n"
                    "  ↓ 建议：观察企稳信号，可考虑逢低布局"
                ),
                "severity": "high",
                "affected": ["纳斯达克", "上证指数"],
            })
        elif vix_price < 12:
            signals.append({
                "name": "VIX 极端平静",
                "narrative": (
                    f"VIX = {vix_price:.2f}（<12） → 市场极度平静\n"
                    "  ↓ 历史上过低 VIX 常伴随后续波动放大\n"
                    "  ↓ 建议：控制仓位，警惕黑天鹅"
                ),
                "severity": "medium",
                "affected": [],
            })

    skew = sentiment.get("SKEW")
    if skew:
        skew_price = skew["price"]
        if skew_price >= 150:
            signals.append({
                "name": "SKEW 尾部风险显著",
                "narrative": (
                    f"SKEW = {skew_price:.2f}（≥150） → 对冲基金显著买入尾部保护\n"
                    "  ↓ 说明大资金担忧黑天鹅事件\n"
                    "  ↓ 传导：警惕美股脆弱性，A 股/港股也可能被拖累"
                ),
                "severity": "medium",
                "affected": ["纳斯达克", "上证指数", "恒生指数"],
            })

    # VIX 与 SKEW 背离（VIX 低但 SKEW 高，市场未定价小概率大风险）
    if vix and skew:
        vix_price = vix["price"]
        skew_price = skew["price"]
        if vix_price < 20 and skew_price >= 145:
            signals.append({
                "name": "VIX-SKEW 背离",
                "narrative": (
                    f"VIX 低 ({vix_price:.2f}) 但 SKEW 高 ({skew_price:.2f}) → 市场表面平静，深处担忧\n"
                    "  ↓ 大资金买保险，散户还在裸奔\n"
                    "  ↓ 建议：控制仓位，警惕大波动"
                ),
                "severity": "medium",
                "affected": ["纳斯达克"],
            })

    return signals
