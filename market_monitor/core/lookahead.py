"""前瞻性观察清单（Lookahead Watchlist）

盘后报告末尾的"明日关注"，让 Steven 不用自己翻日历。
组合三个数据源：
1. 次日宏观事件（econ_calendar.tomorrow_events）
2. 次日个股财报（calendar_events 手工维护）
3. 关键技术位（从 price_alert 配置拉）
"""
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional

from . import econ_calendar as ec
from . import calendar_events as ce
from .config import get_config


# ── 关键技术位 ────────────────────────────────────────────
# 与 price_alert.py 保持一致的关键点位
# 实际运行时从 config 拉取，这里做 fallback
DEFAULT_KEY_LEVELS = {
    "上证指数": {"stop_loss": 3830, "add_position": 4229},
    "创业板指": {"stop_loss": 3756, "add_position": 4147},
    "沪金主力": {"stop_loss": 862, "add_position": 970},
}


def _get_key_levels() -> Dict:
    """从配置拉关键技术位，fallback 用默认值"""
    try:
        cfg = get_config()
        levels = cfg.get("price_alert_levels")
        if levels and isinstance(levels, dict):
            return levels
    except Exception:
        pass
    return DEFAULT_KEY_LEVELS


def _get_current_prices(data: Dict) -> Dict[str, float]:
    """从盘后报告数据里提取当前价格"""
    prices = {}
    indices = data.get("indices", {})
    for name, info in indices.items():
        if isinstance(info, dict) and "close" in info:
            prices[name] = info["close"]
    # 泪金主力可能在 overseas 里（新浪 nf_AU0）
    overseas = data.get("overseas", {})
    for name, info in overseas.items():
        if isinstance(info, dict):
            price = info.get("price") or info.get("close")
            if price and name not in prices:
                prices[name] = price
    return prices


def _format_key_levels(levels: Dict, current_prices: Dict[str, float]) -> List[str]:
    """格式化关键技术位"""
    lines = []
    for name, cfg in levels.items():
        cur = current_prices.get(name)
        sl = cfg.get("stop_loss")
        ap = cfg.get("add_position")
        parts = [name]
        if cur:
            parts.append(f"现 {cur:.2f}")
        if sl:
            parts.append(f"止损 {sl}")
        if ap:
            parts.append(f"加仓 {ap}")
        # 距离止损/加仓的距离
        if cur and sl:
            if cur <= sl:
                parts.append(f"⚠️已破止损位")
            else:
                dist = (cur - sl) / cur * 100
                if dist < 2:
                    parts.append(f"⚠️距止损仅 {dist:.1f}%")
        if cur and ap:
            if cur >= ap:
                parts.append(f"🚀已突破加仓位")
            else:
                dist = (ap - cur) / cur * 100
                if dist < 2:
                    parts.append(f"🎯距加仓仅 {dist:.1f}%")
        lines.append("  📌 " + " | ".join(parts))
    return lines


# ── 主入口 ────────────────────────────────────────────────

def build_tomorrow_watchlist(data: Optional[Dict] = None,
                              min_impact: int = 3) -> str:
    """生成"明日关注"清单。

    Args:
        data: 盘后报告的数据字典（用于提取当前价格做技术位距离计算）
        min_impact: 最低影响力过滤

    Returns:
        格式化好的文本段落，可直接拼接到盘后报告末尾
    """
    lines = ["━━━━━━━━━━━━━━━", "🔭 明日关注"]
    has_content = False

    # 1. 次日宏观事件
    events = ec.tomorrow_events(min_impact=min_impact)
    if events:
        has_content = True
        lines.append("")
        lines.append("📊 宏观事件")
        for e in events:
            time_part = e["time"] if e.get("time") else "全天"
            stars = "⭐" * e["impact_score"]
            detail = ""
            if e.get("forecast") or e.get("previous"):
                parts = []
                if e.get("forecast"):
                    parts.append(f"预期 {e['forecast']}")
                if e.get("previous"):
                    parts.append(f"前值 {e['previous']}")
                detail = f" ({' | '.join(parts)})"
            lines.append(f"  {e['flag']} {time_part} {e['title_zh']} {stars}{detail}")
    else:
        # 用手工日历兜底
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        manual = ce.upcoming(days=1, from_date=tomorrow)
        high = [e for e in manual if e["impact"] >= min_impact]
        if high:
            has_content = True
            lines.append("")
            lines.append("📊 宏观事件")
            for e in high:
                stars = "⭐" * e["impact"]
                lines.append(f"  {e['title']} {stars}")

    # 2. 关键技术位
    levels = _get_key_levels()
    current_prices = _get_current_prices(data) if data else {}
    if levels:
        has_content = True
        lines.append("")
        lines.append("🎯 关键技术位")
        level_lines = _format_key_levels(levels, current_prices)
        lines.extend(level_lines)

    # 3. 交易提示
    tomorrow_weekday = (date.today() + timedelta(days=1)).weekday()
    tips = []
    if tomorrow_weekday == 4:  # 周五
        tips.append("  ⚠️ 明日为周五，注意周末持仓风险")
    elif tomorrow_weekday == 5 or tomorrow_weekday == 6:
        tips.append("  📌 明日为周末，休市")
    if events:
        high_impact = [e for e in events if e["impact_score"] >= 5]
        if high_impact:
            tips.append("  ⚡ 明日有高影响数据发布，注意波动加剧")

    if tips:
        has_content = True
        lines.append("")
        lines.append("💡 交易提示")
        lines.extend(tips)

    if not has_content:
        lines.append("  （明日无重大事件）")

    return "\n".join(lines)


def build_morning_calendar_brief() -> str:
    """晨报用的简版日历摘要（今日事件 + 未来 3 天展望）"""
    lines = []
    has_content = False

    # 今日事件
    today = ec.today_events(min_impact=3)
    if today:
        has_content = True
        lines.append("━━━━━━━━━━━━━━━")
        lines.append("📅 今日财经日历")
        for e in today:
            time_part = e["time"] if e.get("time") else "全天"
            stars = "⭐" * e["impact_score"]
            detail = ""
            if e.get("forecast") or e.get("previous"):
                parts = []
                if e.get("forecast"):
                    parts.append(f"预期 {e['forecast']}")
                if e.get("previous"):
                    parts.append(f"前值 {e['previous']}")
                detail = f" ({' | '.join(parts)})"
            lines.append(f"  {e['flag']} {time_part} {e['title_zh']} {stars}{detail}")

    # 未来 3 天高影响预览
    upcoming = ec.upcoming(days=3, min_impact=4)
    # 排除今天的
    today_str = date.today().strftime("%Y-%m-%d")
    upcoming = [e for e in upcoming if e["date"] != today_str]
    if upcoming:
        has_content = True
        if not lines:
            lines.append("━━━━━━━━━━━━━━━")
        lines.append("📅 未来 3 天关注")
        for e in upcoming[:5]:  # 最多 5 条
            d = datetime.strptime(e["date"], "%Y-%m-%d").date()
            days_from = (d - date.today()).days
            when = "明日" if days_from == 1 else f"{days_from}天后"
            stars = "⭐" * e["impact_score"]
            lines.append(f"  {e['flag']} [{when}] {e['title_zh']} {stars}")

    if not has_content:
        return ""

    return "\n".join(lines)
