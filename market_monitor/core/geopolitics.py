"""地缘事件跟踪（P2-2）

数据源：Google News RSS（中文 + 英文）
- 关键词组：制裁 / 关税 / 贸易战 / 俄乌 / 中东 / 台海 / 半导体禁令 等
- 6h 缓存

核心接口：
- fetch_geo_events(hours: int = 24) -> List[Dict]
- format_geo_brief(events, top: int = 5) -> str  # 给人看
- geo_summary_for_ai(events, top: int = 8) -> str  # 给 AI 看
- classify_impact(events) -> List[Dict]  # 结构化：category + severity + market_link
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

# ---------- 关键词组 ----------
# 中文覆盖：地缘冲突 / 制裁 / 关税 / 贸易战 / 军事事件
_ZH_QUERY = "地缘政治 OR 制裁 OR 关税 OR 贸易战 OR 中东局势 OR 俄乌冲突 OR 台海 OR 半导体禁令 OR 出口管制"
# 英文覆盖：sanctions / trade war / tariff / Middle East / OPEC / Fed
_EN_QUERY = "sanctions OR \"trade war\" OR tariff OR \"middle east\" OR \"Russia Ukraine\" OR \"South China Sea\" OR \"chip ban\" OR \"export control\""

# ---------- 缓存 ----------
_CACHE_DIR = os.path.expanduser("~/.openclaw/workspace/state")
_CACHE_FILE = os.path.join(_CACHE_DIR, "geo_events_cache.json")
_CACHE_TTL_SEC = 6 * 3600  # 6h

# ---------- 分类关键词 ----------
# category → (severity, keywords)  keyword 命中即归类；先命中先出
_CATEGORY_RULES = [
    ("military_conflict", "high", [
        "战争", "空袭", "导弹", "轰炸", "war", "airstrike", "missile",
        "invasion", "military strike", "occupation",
    ]),
    ("sanctions", "high", [
        "制裁", "sanctions", "sanction", "SDN", "asset freeze",
        "禁令", "禁运",
    ]),
    ("tariff_trade", "medium", [
        "关税", "贸易战", "tariff", "trade war", "trade dispute",
        "对等关税", "报复性关税",
    ]),
    ("tech_export_control", "high", [
        "半导体禁令", "芯片禁令", "chip ban", "chip export", "EDA ban",
        "出口管制", "export control", "entity list",
    ]),
    ("central_bank_action", "medium", [
        "Fed rate", "ECB rate", "BOJ intervention", "PBoC",
        "加息", "降息", "干预", "SDR",
    ]),
    ("election_political", "medium", [
        "election", "election result", "总统大选", "国会",
        "coup", "政变", "impeachment",
    ]),
    ("oil_energy", "medium", [
        "OPEC", "opec+", "oil production", "石油", "原油",
        "energy embargo", "能源禁运",
    ]),
    ("taiwan_strait", "high", [
        "台海", "台湾", "Taiwan Strait", "Taiwan",
    ]),
    ("supply_chain", "low", [
        "supply chain", "供应链", "chip shortage", "芯片荒",
    ]),
]

# category → 市场影响标签（帮 AI 联动分析）
_CATEGORY_MARKET_LINK = {
    "military_conflict": "避险情绪 → 金/USD/JPY 涨，风险资产/EM 承压",
    "sanctions": "被制裁方资产承压；关联产业链（能源/科技）供给受扰",
    "tariff_trade": "出口链承压；A/H 股外贸股受冲击，人民币汇率承压",
    "tech_export_control": "半导体/科技板块波动；国产替代主题受益",
    "central_bank_action": "利率敏感资产（成长股/黄金/长债）反应剧烈",
    "election_political": "政策不确定性上升；本币波动加剧",
    "oil_energy": "原油价格波动 → 能源/航空/化工连锁反应",
    "taiwan_strait": "亚太风险偏好回落；地缘避险资产受追捧",
    "supply_chain": "相关产业链短期扰动；关注库存周期",
}


def _http_get_rss(query: str, hl: str, gl: str, ceid: str, timeout: int = 8) -> str:
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="replace")


def _parse_rss(raw: str, source_lang: str = "zh") -> List[Dict]:
    """粗暴解析 Google News RSS 的 items。"""
    items = re.findall(r"<item>(.*?)</item>", raw, re.DOTALL)
    result: List[Dict] = []
    for it in items:
        title_m = re.search(r"<title>(.*?)</title>", it)
        date_m = re.search(r"<pubDate>(.*?)</pubDate>", it)
        src_m = re.search(r"<source[^>]*>(.*?)</source>", it)
        link_m = re.search(r"<link>(.*?)</link>", it)
        if not title_m:
            continue
        title = title_m.group(1).strip()
        # 去掉 " - 媒体名" 尾巴
        title_clean = re.sub(r" - [^-]+$", "", title)
        result.append({
            "title": title_clean,
            "raw_title": title,
            "source": src_m.group(1).strip() if src_m else "",
            "pub_date": date_m.group(1).strip() if date_m else "",
            "link": link_m.group(1).strip() if link_m else "",
            "lang": source_lang,
        })
    return result


def _parse_pub_date(pub_str: str) -> Optional[datetime]:
    """RFC 822 → datetime (UTC)"""
    if not pub_str:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S GMT"):
        try:
            dt = datetime.strptime(pub_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _load_cache() -> Optional[Dict]:
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
        if time.time() - cache.get("ts", 0) < _CACHE_TTL_SEC:
            return cache
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _save_cache(events: List[Dict]) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "events": events}, f, ensure_ascii=False)
    except OSError as e:  # noqa: BLE001
        print(f"[geopolitics] 缓存写入失败: {e}", file=sys.stderr)


def fetch_geo_events(hours: int = 24, use_cache: bool = True) -> List[Dict]:
    """拉取最近 N 小时的地缘事件（中英双语）。

    Args:
        hours: 只保留 pub_date 在 now - hours 之内的事件
        use_cache: 是否用 6h 缓存
    Returns:
        List[Dict] with keys: title, source, pub_date, link, lang, category, severity
    """
    if use_cache:
        cache = _load_cache()
        if cache and cache.get("events"):
            events = cache["events"]
        else:
            events = _fetch_fresh()
            _save_cache(events)
    else:
        events = _fetch_fresh()

    # 按 hours 过滤
    if hours > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        filtered = []
        for ev in events:
            dt = _parse_pub_date(ev.get("pub_date", ""))
            if dt is None or dt >= cutoff:
                filtered.append(ev)
        events = filtered

    # 分类
    for ev in events:
        cat, sev = _classify(ev["title"])
        ev["category"] = cat
        ev["severity"] = sev
        ev["market_link"] = _CATEGORY_MARKET_LINK.get(cat, "")

    return events


def _fetch_fresh() -> List[Dict]:
    result: List[Dict] = []
    try:
        raw = _http_get_rss(_ZH_QUERY, hl="zh-CN", gl="CN", ceid="CN:zh-Hans")
        result.extend(_parse_rss(raw, source_lang="zh"))
    except Exception as e:  # noqa: BLE001
        print(f"[geopolitics] ZH RSS 拉取失败: {e}", file=sys.stderr)
    try:
        raw = _http_get_rss(_EN_QUERY, hl="en", gl="US", ceid="US:en")
        result.extend(_parse_rss(raw, source_lang="en"))
    except Exception as e:  # noqa: BLE001
        print(f"[geopolitics] EN RSS 拉取失败: {e}", file=sys.stderr)

    # 去重（title 标准化）
    seen = set()
    deduped = []
    for ev in result:
        key = re.sub(r"\s+", "", ev["title"]).lower()[:40]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)
    return deduped


def _classify(title: str) -> tuple:
    """返回 (category, severity)。命中不到则 unclassified/low。"""
    t = title.lower()
    for cat, sev, keywords in _CATEGORY_RULES:
        for kw in keywords:
            if kw.lower() in t:
                return cat, sev
    return "unclassified", "low"


# ---------- 展示 ----------
_CATEGORY_LABEL = {
    "military_conflict": "🔥 军事冲突",
    "sanctions": "🚫 制裁",
    "tariff_trade": "📦 关税贸易",
    "tech_export_control": "🔒 科技出口管制",
    "central_bank_action": "🏦 央行动作",
    "election_political": "🗳️ 政治选举",
    "oil_energy": "🛢️ 石油能源",
    "taiwan_strait": "⚓ 台海",
    "supply_chain": "📦 供应链",
    "unclassified": "•",
}

_SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def format_geo_brief(events: List[Dict], top: int = 8) -> str:
    """给人看：按 severity + 分类聚合。"""
    if not events:
        return "🌐 地缘事件监控：近 24h 未发现明显重大地缘事件"

    # 只保留分类过的（unclassified 可能是噪音）
    classified = [e for e in events if e.get("category") != "unclassified"]
    if not classified:
        return "🌐 地缘事件监控：近 24h 无高影响地缘事件"

    # 按 severity 排序，再按 category 分组
    classified.sort(key=lambda x: _SEV_ORDER.get(x.get("severity"), 3))

    # 分类聚合
    by_cat: Dict[str, List[Dict]] = {}
    for ev in classified[:top * 2]:
        by_cat.setdefault(ev["category"], []).append(ev)

    lines = ["🌐 地缘事件监控（近 24h）:"]
    total_shown = 0
    for cat, evs in by_cat.items():
        if total_shown >= top:
            break
        label = _CATEGORY_LABEL.get(cat, cat)
        lines.append(f"\n{label}:")
        for ev in evs[:3]:
            lines.append(f"  • {ev['title']}（{ev.get('source','?')}）")
            total_shown += 1
            if total_shown >= top:
                break
    return "\n".join(lines)


def geo_summary_for_ai(events: List[Dict], top: int = 8) -> str:
    """给 AI 看：包含市场影响标签，便于叙事关联。"""
    classified = [e for e in events if e.get("category") != "unclassified"]
    if not classified:
        return "【地缘事件】近 24h 无重大地缘事件"

    classified.sort(key=lambda x: _SEV_ORDER.get(x.get("severity"), 3))

    lines = ["【地缘事件（近 24h）】"]
    for ev in classified[:top]:
        cat_label = _CATEGORY_LABEL.get(ev["category"], ev["category"])
        market = ev.get("market_link", "")
        lines.append(
            f"- [{ev['severity'].upper()}] {cat_label} · {ev['title']}"
            + (f" ⇒ {market}" if market else "")
        )
    return "\n".join(lines)


def classify_impact(events: List[Dict]) -> List[Dict]:
    """返回按 category 聚合的结构化 impact 报告。"""
    if not events:
        return []

    classified = [e for e in events if e.get("category") != "unclassified"]
    if not classified:
        return []

    grouped: Dict[str, List[Dict]] = {}
    for ev in classified:
        grouped.setdefault(ev["category"], []).append(ev)

    result: List[Dict] = []
    for cat, evs in grouped.items():
        # 该分类下最高 severity
        sev = min((_SEV_ORDER.get(e["severity"], 3) for e in evs))
        sev_label = ["high", "medium", "low"][sev] if sev < 3 else "low"
        result.append({
            "category": cat,
            "label": _CATEGORY_LABEL.get(cat, cat),
            "severity": sev_label,
            "count": len(evs),
            "market_link": _CATEGORY_MARKET_LINK.get(cat, ""),
            "sample_titles": [e["title"] for e in evs[:3]],
        })

    # 按 severity 排序
    result.sort(key=lambda x: _SEV_ORDER.get(x["severity"], 3))
    return result
