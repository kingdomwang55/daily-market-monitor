"""财经日历（ForexFactory 数据源 + 手工日历融合）

数据源：
1. ForexFactory JSON（本周所有事件，含预期值/前值/影响级别）
   https://nfs.faireconomy.media/ff_calendar_thisweek.json
2. calendar_events.py（手工维护 · 中期展望 + 中国政策/财报）

融合规则：
- 本周内的事件：优先 ForexFactory（有预期值），手工日历作为兜底
- 本周外的事件（>7 天）：仅从手工日历取
- 影响级别：ForexFactory 用 High/Medium/Low → 转 1-5 分对齐手工日历

发布时间敏感数据：
- 非农 / CPI / PPI / FOMC 有具体 HH:MM，可用于精准触发
- 中国数据 ForexFactory 覆盖弱，主要依赖手工日历
"""
import urllib.request
import json
import sys
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Optional
from pathlib import Path

from . import calendar_events


# ── ForexFactory ────────────────────────────────────────────
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FF_CACHE_PATH = Path.home() / ".openclaw" / "workspace" / "state" / "ff_calendar_cache.json"
FF_CACHE_TTL_HOURS = 2  # 数据每 2 小时刷新一次已足够

# ForexFactory impact → 影响力分数（对齐手工日历的 1-5 分）
FF_IMPACT_SCORE = {
    "High": 5,
    "Medium": 3,
    "Low": 2,
    "Holiday": 1,
}

# 主要关注的国家（其余可忽略）
FF_MAJOR_COUNTRIES = {"USD", "CNY", "EUR", "JPY", "GBP"}

# 中国事件用中文标题映射（ForexFactory 是英文）
FF_TITLE_ZH = {
    "CPI y/y": "CPI 同比",
    "PPI y/y": "PPI 同比",
    "GDP q/y": "GDP 同比",
    "Trade Balance": "贸易差额",
    "Non-Farm Employment Change": "非农就业变化",
    "Unemployment Rate": "失业率",
    "ISM Services PMI": "ISM 服务业 PMI",
    "ISM Manufacturing PMI": "ISM 制造业 PMI",
    "Core CPI m/m": "核心 CPI 环比",
    "Retail Sales m/m": "零售销售环比",
    "FOMC Meeting Minutes": "FOMC 会议纪要",
    "FOMC Statement": "FOMC 利率决议",
    "Federal Funds Rate": "联邦基金利率",
    "Fed Chair Powell Speaks": "鲍威尔讲话",
}

# 国家 → emoji
COUNTRY_FLAG = {
    "USD": "🇺🇸",
    "CNY": "🇨🇳",
    "EUR": "🇪🇺",
    "JPY": "🇯🇵",
    "GBP": "🇬🇧",
    "AUD": "🇦🇺",
    "CAD": "🇨🇦",
    "CHF": "🇨🇭",
    "NZD": "🇳🇿",
}


def _cache_valid() -> bool:
    """检查本地缓存是否还新鲜"""
    if not FF_CACHE_PATH.exists():
        return False
    try:
        age_sec = datetime.now().timestamp() - FF_CACHE_PATH.stat().st_mtime
        return age_sec < FF_CACHE_TTL_HOURS * 3600
    except OSError:
        return False


def _load_cache() -> List[Dict]:
    try:
        with open(FF_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def _save_cache(events: List[Dict]) -> None:
    try:
        FF_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FF_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[econ_calendar] cache save failed: {e}", file=sys.stderr)


def fetch_forexfactory(use_cache: bool = True) -> List[Dict]:
    """拉取 ForexFactory 本周财经日历。

    Returns:
        [{
            "date": "2026-07-08",       # YYYY-MM-DD (北京时间)
            "time": "09:30",            # HH:MM (北京时间)
            "datetime_bj": "2026-07-08T09:30:00+08:00",
            "country": "USD",
            "flag": "🇺🇸",
            "title": "Non-Farm Employment Change",
            "title_zh": "非农就业变化",
            "impact": "High",
            "impact_score": 5,
            "forecast": "180K",
            "previous": "175K",
            "source": "forexfactory",
        }, ...]
        按 datetime_bj 升序
    """
    if use_cache and _cache_valid():
        return _load_cache()

    try:
        req = urllib.request.Request(FF_URL, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
        events = json.loads(raw)
    except Exception as e:
        print(f"[econ_calendar] fetch ForexFactory failed: {e}", file=sys.stderr)
        # fallback: 尝试用旧缓存
        if FF_CACHE_PATH.exists():
            print(f"[econ_calendar] using stale cache", file=sys.stderr)
            return _load_cache()
        return []

    bj_tz = timezone(timedelta(hours=8))
    normalized = []
    for e in events:
        try:
            # e['date'] 类似 "2026-07-08T21:30:00-04:00"
            dt = datetime.fromisoformat(e["date"])
            dt_bj = dt.astimezone(bj_tz)
        except (ValueError, KeyError):
            continue

        country = e.get("country", "")
        title = e.get("title", "")
        normalized.append({
            "date": dt_bj.strftime("%Y-%m-%d"),
            "time": dt_bj.strftime("%H:%M"),
            "datetime_bj": dt_bj.isoformat(),
            "country": country,
            "flag": COUNTRY_FLAG.get(country, "🌐"),
            "title": title,
            "title_zh": FF_TITLE_ZH.get(title, title),
            "impact": e.get("impact", "Low"),
            "impact_score": FF_IMPACT_SCORE.get(e.get("impact", "Low"), 1),
            "forecast": e.get("forecast", "") or "",
            "previous": e.get("previous", "") or "",
            "source": "forexfactory",
        })

    normalized.sort(key=lambda x: x["datetime_bj"])
    _save_cache(normalized)
    return normalized


# ── 融合视图 ────────────────────────────────────────────────

def _dedupe_key(title: str) -> str:
    """归一化事件标题，用于跨源去重"""
    t = title.lower()
    if "cpi" in t and "core" not in t:
        return "cpi"
    if "core cpi" in t:
        return "core_cpi"
    if "ppi" in t:
        return "ppi"
    if "non-farm" in t or "nfp" in t or "非农" in t:
        return "nfp"
    if "fomc" in t or "利率决议" in t:
        return "fomc"
    if "unemployment" in t:
        return "unemployment"
    if "ism services" in t:
        return "ism_services"
    if "ism manufacturing" in t:
        return "ism_mfg"
    return t[:30]


def get_events(from_date: Optional[str] = None,
               days: int = 7,
               min_impact: int = 3,
               countries: Optional[List[str]] = None) -> List[Dict]:
    """获取融合后的事件列表（ForexFactory + 手工日历）。

    Args:
        from_date: 起始日期 YYYY-MM-DD（默认今天）
        days: 未来天数窗口
        min_impact: 最低影响力分数（1-5），默认 3
        countries: 只保留这些国家（USD/CNY/...），None 为默认主要国家

    Returns:
        统一格式事件列表（按日期+时间升序）
    """
    if from_date:
        start = datetime.strptime(from_date, "%Y-%m-%d").date()
    else:
        start = date.today()
    end = start + timedelta(days=days)

    if countries is None:
        countries = list(FF_MAJOR_COUNTRIES)

    # 1. ForexFactory
    ff_events = fetch_forexfactory()
    ff_in_range = []
    seen_keys = set()  # date + dedupe_key，用于跨源去重
    for e in ff_events:
        try:
            d = datetime.strptime(e["date"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (start <= d <= end):
            continue
        if e["country"] not in countries:
            continue
        if e["impact_score"] < min_impact:
            continue
        ff_in_range.append(e)
        seen_keys.add((e["date"], _dedupe_key(e["title"])))

    # 2. 手工日历（补 ForexFactory 拿不到的部分：中国数据、中期财报、中期政策）
    manual_events = calendar_events.upcoming(days=days, from_date=start.strftime("%Y-%m-%d"))
    manual_in_range = []
    for e in manual_events:
        if e["impact"] < min_impact:
            continue
        # 手工日历没有 country 字段，按分类推断
        cat = e.get("category", "")
        country = {"美联储": "USD", "美国数据": "USD", "美股财报": "USD",
                   "中国数据": "CNY", "中国政策": "CNY"}.get(cat, "USD")
        if country not in countries:
            continue
        # 去重：已有 ForexFactory 数据的日期+事件类型
        key = (e["date"], _dedupe_key(e["title"]))
        if key in seen_keys:
            continue
        manual_in_range.append({
            "date": e["date"],
            "time": "",  # 手工日历不带时间
            "datetime_bj": f"{e['date']}T23:59:00+08:00",  # 排序用兜底
            "country": country,
            "flag": COUNTRY_FLAG.get(country, "🌐"),
            "title": e["title"],
            "title_zh": e["title"],  # 手工日历本来就是中文
            "impact": {5: "High", 4: "High", 3: "Medium", 2: "Low", 1: "Low"}[e["impact"]],
            "impact_score": e["impact"],
            "forecast": "",
            "previous": "",
            "source": "manual",
            "category": cat,
        })

    all_events = ff_in_range + manual_in_range
    all_events.sort(key=lambda x: (x["date"], x.get("time", "99:99") or "99:99"))
    return all_events


def today_events(min_impact: int = 3, countries: Optional[List[str]] = None) -> List[Dict]:
    """今日事件（含时间字段）"""
    return get_events(from_date=None, days=0, min_impact=min_impact, countries=countries)


def tomorrow_events(min_impact: int = 3, countries: Optional[List[str]] = None) -> List[Dict]:
    """次日事件（盘后报告的"明日关注"用）"""
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    return get_events(from_date=tomorrow, days=0, min_impact=min_impact, countries=countries)


def upcoming(days: int = 7, min_impact: int = 3,
             countries: Optional[List[str]] = None) -> List[Dict]:
    """未来 N 日高影响事件"""
    return get_events(from_date=None, days=days,
                      min_impact=min_impact, countries=countries)


# ── 格式化 ────────────────────────────────────────────────

def format_event_line(e: Dict) -> str:
    """把单个事件格式化成一行文本"""
    time_part = f"{e['time']}" if e.get("time") else "全天"
    stars = "⭐" * e["impact_score"]
    parts = [f"{e['flag']} {time_part}", e["title_zh"], stars]
    if e.get("forecast") or e.get("previous"):
        detail = []
        if e.get("forecast"):
            detail.append(f"预期 {e['forecast']}")
        if e.get("previous"):
            detail.append(f"前值 {e['previous']}")
        if detail:
            parts.append(f"({' | '.join(detail)})")
    return "  " + " ".join(parts)


def format_events(events: List[Dict], title: str = "财经日历") -> str:
    """把事件列表格式化成人类可读文本"""
    if not events:
        return f"【{title}】\n  （无重要事件）"

    lines = [f"【{title}】"]
    # 按日期分组
    by_date = {}
    for e in events:
        by_date.setdefault(e["date"], []).append(e)

    for date_str in sorted(by_date.keys()):
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        days_from = (d - date.today()).days
        when = "今日" if days_from == 0 else ("明日" if days_from == 1 else f"{days_from}天后")
        lines.append(f"\n📅 {date_str} · {when}")
        for e in by_date[date_str]:
            lines.append(format_event_line(e))

    return "\n".join(lines)
