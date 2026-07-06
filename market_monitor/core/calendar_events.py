"""宏观事件日历

包含：
- 美联储 FOMC 会议
- 中国主要经济数据发布（CPI/PPI/PMI/社融）
- 美国主要经济数据（CPI/PPI/NFP/GDP）
- 大厂财报季关键节点

数据来源：官方公布日程 + 常规发布规律
维护方式：每季度手动更新一次即可

如果要接自动化：
- akshare.macro_bank_usa_fomc  → FOMC 日程
- akshare.macro_china_cpi_yearly → 中国经济数据
- 财报接 finnhub/alpha vantage API
"""
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional


# ── 2026 年宏观事件（人工维护） ──────────────────────────────
# 格式: (日期 YYYY-MM-DD, 分类, 标题, 影响力 1-5)
# 影响力: 5=市场级重磅 / 4=行业级 / 3=值得关注 / 2=一般 / 1=次要
_EVENTS_2026 = [
    # ─── 美联储 FOMC（2026 全年 8 次）───
    ("2026-01-28", "美联储", "FOMC 利率决议 + Powell 记者会", 5),
    ("2026-03-18", "美联储", "FOMC 利率决议 + 经济预测", 5),
    ("2026-05-06", "美联储", "FOMC 利率决议", 5),
    ("2026-06-17", "美联储", "FOMC 利率决议 + 经济预测", 5),
    ("2026-07-29", "美联储", "FOMC 利率决议", 5),
    ("2026-09-16", "美联储", "FOMC 利率决议 + 经济预测", 5),
    ("2026-11-04", "美联储", "FOMC 利率决议", 5),
    ("2026-12-16", "美联储", "FOMC 利率决议 + 经济预测", 5),

    # ─── Jackson Hole 全球央行年会 ───
    ("2026-08-20", "美联储", "Jackson Hole 央行年会（3 日）", 4),

    # ─── 美国关键数据（月度发布，日期规律估算）───
    # NFP 非农：每月第一个周五
    # CPI：每月 10-15 日
    # PPI：每月 12-16 日
    # 简化：只标关键月份的粗略日期
    ("2026-07-11", "美国数据", "美国 6 月 CPI", 5),
    ("2026-07-15", "美国数据", "美国 6 月 PPI", 4),
    ("2026-08-01", "美国数据", "美国 7 月非农就业（NFP）", 5),
    ("2026-08-12", "美国数据", "美国 7 月 CPI", 5),
    ("2026-09-05", "美国数据", "美国 8 月非农就业", 5),
    ("2026-09-11", "美国数据", "美国 8 月 CPI", 5),
    ("2026-10-03", "美国数据", "美国 9 月非农就业", 5),
    ("2026-10-15", "美国数据", "美国 9 月 CPI", 5),
    ("2026-11-07", "美国数据", "美国 10 月非农就业", 5),
    ("2026-11-13", "美国数据", "美国 10 月 CPI", 5),
    ("2026-12-05", "美国数据", "美国 11 月非农就业", 5),
    ("2026-12-10", "美国数据", "美国 11 月 CPI", 5),

    # ─── 中国关键数据 ───
    ("2026-07-09", "中国数据", "6 月 CPI/PPI", 4),
    ("2026-07-15", "中国数据", "6 月经济数据（GDP、社零、工业增加值）", 5),
    ("2026-07-31", "中国数据", "7 月官方 PMI", 4),
    ("2026-08-09", "中国数据", "7 月 CPI/PPI", 4),
    ("2026-08-15", "中国数据", "7 月经济数据", 4),
    ("2026-08-31", "中国数据", "8 月官方 PMI", 4),
    ("2026-09-09", "中国数据", "8 月 CPI/PPI", 4),
    ("2026-09-15", "中国数据", "8 月经济数据", 4),
    ("2026-09-30", "中国数据", "9 月官方 PMI", 4),
    ("2026-10-14", "中国数据", "9 月 CPI/PPI", 4),
    ("2026-10-19", "中国数据", "三季度 GDP + 9 月经济数据", 5),
    ("2026-10-31", "中国数据", "10 月官方 PMI", 4),
    ("2026-11-09", "中国数据", "10 月 CPI/PPI", 4),
    ("2026-11-14", "中国数据", "10 月经济数据", 4),
    ("2026-11-30", "中国数据", "11 月官方 PMI", 4),
    ("2026-12-09", "中国数据", "11 月 CPI/PPI", 4),
    ("2026-12-15", "中国数据", "11 月经济数据", 4),
    ("2026-12-31", "中国数据", "12 月官方 PMI", 4),

    # ─── 中国重大会议（示意，具体日期以官宣为准）───
    ("2026-10-20", "中国政策", "十四届四中全会（预计）", 5),
    ("2026-12-10", "中国政策", "中央经济工作会议（预计）", 5),

    # ─── 大厂财报季（Q2 财报 2026-07 - 2026-08）───
    # 具体日期以官方公告为准，这里给业界惯例日期
    ("2026-07-24", "美股财报", "Tesla Q2（盘后）", 5),
    ("2026-07-30", "美股财报", "Meta Q2（盘后）", 5),
    ("2026-07-30", "美股财报", "Microsoft Q2（盘后）", 5),
    ("2026-07-31", "美股财报", "Apple Q3 财年（盘后）", 5),
    ("2026-07-31", "美股财报", "Amazon Q2（盘后）", 5),
    ("2026-08-06", "美股财报", "AMD Q2（盘后）", 5),
    ("2026-08-27", "美股财报", "NVIDIA Q2 财年（盘后）", 5),

    # ─── 大厂财报季（Q3 财报 2026-10 - 2026-11）───
    ("2026-10-22", "美股财报", "Tesla Q3", 5),
    ("2026-10-29", "美股财报", "Meta Q3", 5),
    ("2026-10-29", "美股财报", "Microsoft Q3", 5),
    ("2026-10-30", "美股财报", "Apple Q4 财年", 5),
    ("2026-10-30", "美股财报", "Amazon Q3", 5),
    ("2026-11-05", "美股财报", "AMD Q3", 5),
    ("2026-11-19", "美股财报", "NVIDIA Q3 财年", 5),
]


def upcoming(days: int = 7, from_date: Optional[str] = None) -> List[Dict]:
    """获取未来 N 天的宏观事件。

    Args:
        days: 未来天数
        from_date: 起始日期 YYYY-MM-DD（默认今天）

    Returns:
        [{"date": "2026-07-11", "category": "美国数据",
          "title": "美国 6 月 CPI", "impact": 5, "days_from_now": 5}]
    """
    if from_date:
        start = datetime.strptime(from_date, "%Y-%m-%d").date()
    else:
        start = date.today()
    end = start + timedelta(days=days)

    results = []
    for d_str, cat, title, impact in _EVENTS_2026:
        try:
            d = datetime.strptime(d_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        if start <= d <= end:
            days_from = (d - start).days
            results.append({
                "date": d_str,
                "category": cat,
                "title": title,
                "impact": impact,
                "days_from_now": days_from,
            })

    return sorted(results, key=lambda x: (x["date"], -x["impact"]))


def in_month(year: int, month: int) -> List[Dict]:
    """获取某月的所有宏观事件"""
    prefix = f"{year:04d}-{month:02d}-"
    results = []
    for d_str, cat, title, impact in _EVENTS_2026:
        if d_str.startswith(prefix):
            results.append({
                "date": d_str,
                "category": cat,
                "title": title,
                "impact": impact,
            })
    return sorted(results, key=lambda x: (x["date"], -x["impact"]))


def format_events(events: List[Dict], show_days_from_now: bool = True) -> str:
    """把事件列表格式化成人类可读文本"""
    if not events:
        return "（暂无宏观事件）"

    # 按分类分组
    by_cat = {}
    for e in events:
        by_cat.setdefault(e["category"], []).append(e)

    # 分类排序：美联储 > 美国数据 > 中国数据 > 中国政策 > 美股财报
    cat_order = ["美联储", "美国数据", "中国数据", "中国政策", "美股财报"]
    lines = []
    for cat in cat_order:
        if cat not in by_cat:
            continue
        events_of_cat = by_cat[cat]
        icon = {
            "美联储": "🏛️", "美国数据": "🇺🇸", "中国数据": "🇨🇳",
            "中国政策": "🎯", "美股财报": "📊",
        }.get(cat, "📌")
        lines.append(f"{icon} **{cat}**")
        for e in events_of_cat:
            impact_stars = "⭐" * e["impact"]
            if show_days_from_now and "days_from_now" in e:
                d = e["days_from_now"]
                when = "今日" if d == 0 else ("明日" if d == 1 else f"{d}天后")
                lines.append(f"  • [{e['date']} · {when}] {e['title']} {impact_stars}")
            else:
                # 只显示日期部分（月-日）
                short_date = e["date"][5:]
                lines.append(f"  • [{short_date}] {e['title']} {impact_stars}")
        lines.append("")

    return "\n".join(lines).rstrip()
