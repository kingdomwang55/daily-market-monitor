"""全球宏观 & 财经新闻数据源

四合一取数模块（用于 macro_monitor）：
- 🏛️ 政策速递: Fed / SEC / Treasury 官方 RSS
- 📰 财经快讯: NewsNow API (华尔街见闻/财联社/金十/MktNews/FastBull)
- 📈 A股&港股焦点: NewsNow API (雪球热股/A股相关)
- 🌐 全球宏观: Yahoo Finance / 36氪 快讯

每条新闻输出统一格式：
{
    "id": "唯一hash",
    "category": "policy/finance/astock/global",
    "source": "fed/sec/wallstreetcn-quick/xueqiu-hotstock/...",
    "timestamp": "2026-07-06 15:30",
    "text": "新闻标题/正文",
    "link": "原文链接",
}
"""
import hashlib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Dict, Optional


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

CN_TZ = timezone(timedelta(hours=8))

# NewsNow API 基础
NEWSNOW_BASE = "https://newsnow.busiyi.world/api/s"

# 分类 → NewsNow source ID 映射
NEWSNOW_SOURCES = {
    "finance": [
        "wallstreetcn-quick",   # 华尔街见闻实时（最勤）
        "cls-telegraph",        # 财联社电报
        "jin10",                # 金十快讯
        "mktnews-flash",        # MktNews 全球
        "fastbull-news",        # FastBull
        "gelonghui-shijian",    # 格隆汇
    ],
    "astock": [
        "xueqiu-hotstock",      # 雪球热门股
        "xueqiu-remengupiao",   # 雪球热门股票
        "cls-depth",            # 财联社深度
        "wallstreetcn-hot",     # 华尔街见闻热门
    ],
    # 舆情类，可选
    "sentiment": [
        "weibo",
        "zhihu",
    ],
}

# RSS 源（政策类）
RSS_SOURCES = {
    "policy": [
        ("Fed-PressAll", "https://www.federalreserve.gov/feeds/press_all.xml"),
        ("Fed-Speeches", "https://www.federalreserve.gov/feeds/speeches.xml"),
        ("SEC-Press",    "https://www.sec.gov/news/pressreleases.rss"),
    ],
    "global": [
        ("Yahoo-Finance", "https://finance.yahoo.com/news/rssindex"),
        ("36Kr",          "https://36kr.com/feed"),
    ],
}


# ============ 工具函数 ============

def _fetch(url: str, timeout: int = 10) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        return urllib.request.urlopen(req, timeout=timeout).read()
    except Exception as e:
        print(f"[news_sources] fetch failed: {url[:80]} -> {e}", file=sys.stderr)
        return None


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _hash_id(source: str, link: str, text: str) -> str:
    key = f"{source}|{link}|{text[:100]}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


def _ts_from_ms(ms: int) -> str:
    """毫秒时间戳 → 北京时间字符串"""
    try:
        dt = datetime.fromtimestamp(ms / 1000, tz=CN_TZ)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _ts_from_rss_date(s: str) -> Optional[datetime]:
    """RSS pubDate → datetime(CN)"""
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(CN_TZ)
    except Exception:
        return None


# ============ NewsNow API ============

def fetch_newsnow(source_id: str, hours: int = 6,
                  limit: int = 30) -> List[Dict]:
    """从 NewsNow API 拉取指定源

    Args:
        source_id: NewsNow 的 source_id，如 wallstreetcn-quick
        hours: 回溯小时数
        limit: 最多返回条数
    """
    url = f"{NEWSNOW_BASE}?id={source_id}"
    raw = _fetch(url, timeout=10)
    if not raw:
        return []
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        print(f"[fetch_newsnow] {source_id} json parse error: {e}", file=sys.stderr)
        return []

    if data.get("error"):
        print(f"[fetch_newsnow] {source_id} error: {data.get('message')}", file=sys.stderr)
        return []

    items = data.get("items", [])
    if not items:
        return []

    cutoff = datetime.now(CN_TZ) - timedelta(hours=hours)
    out = []
    for it in items[:limit * 2]:  # 拉多一点，过滤后再截
        title = (it.get("title") or "").strip()
        if not title:
            continue

        # 时间处理：pubDate 优先，其次 extra.date，都没有就用当前时间
        pub_ms = it.get("pubDate")
        if not pub_ms:
            extra = it.get("extra") or {}
            pub_ms = extra.get("date")

        # pubDate 可能是 ISO 字符串（mktnews-flash）
        if isinstance(pub_ms, str):
            try:
                dt = datetime.fromisoformat(pub_ms.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_cn = dt.astimezone(CN_TZ)
            except Exception:
                dt_cn = None
        elif isinstance(pub_ms, (int, float)):
            try:
                dt_cn = datetime.fromtimestamp(pub_ms / 1000, tz=CN_TZ)
            except Exception:
                dt_cn = None
        else:
            dt_cn = None

        # 无时间戳的（如雪球热股）视为当前时间，全部保留
        if dt_cn is None:
            dt_cn = datetime.now(CN_TZ)
        elif dt_cn < cutoff:
            continue

        link = it.get("url") or it.get("mobileUrl") or ""

        # 雪球热股附带涨跌幅信息，拼到标题里
        extra = it.get("extra") or {}
        info = extra.get("info") or ""
        if info and info not in title:
            display_text = f"{title} ({info})"
        else:
            display_text = title

        out.append({
            "id": _hash_id(source_id, link, title),
            "category": "",  # 由调用方填
            "source": source_id,
            "timestamp": dt_cn.strftime("%Y-%m-%d %H:%M"),
            "text": display_text,
            "link": link,
        })

    return out[:limit]


# ============ RSS ============

def fetch_rss(name: str, url: str, hours: int = 12,
              limit: int = 30) -> List[Dict]:
    """通用 RSS 拉取"""
    raw = _fetch(url, timeout=10)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"[fetch_rss] {name} parse error: {e}", file=sys.stderr)
        return []

    cutoff = datetime.now(CN_TZ) - timedelta(hours=hours)
    out = []
    for item in root.findall(".//item")[:limit * 2]:
        pub_raw = (item.findtext("pubDate") or "").strip()
        dt_cn = _ts_from_rss_date(pub_raw) if pub_raw else None
        if dt_cn and dt_cn < cutoff:
            continue

        title = _clean_html(item.findtext("title") or "")
        desc = _clean_html(item.findtext("description") or "")
        link = (item.findtext("link") or "").strip()
        text = title if title else desc
        if not text:
            continue

        if not dt_cn:
            dt_cn = datetime.now(CN_TZ)

        out.append({
            "id": _hash_id(name, link, text),
            "category": "",
            "source": name.lower(),
            "timestamp": dt_cn.strftime("%Y-%m-%d %H:%M"),
            "text": text,
            "link": link,
        })
    return out[:limit]


# ============ 分类聚合 ============

def fetch_policy(hours: int = 12) -> List[Dict]:
    """政策速递: Fed / SEC"""
    out = []
    for name, url in RSS_SOURCES["policy"]:
        items = fetch_rss(name, url, hours=hours, limit=15)
        for it in items:
            it["category"] = "policy"
        out.extend(items)
    out.sort(key=lambda x: x["timestamp"], reverse=True)
    return out


def fetch_finance(hours: int = 6) -> List[Dict]:
    """财经快讯: 华尔街见闻/财联社/金十/MktNews/FastBull/格隆汇"""
    out = []
    for src in NEWSNOW_SOURCES["finance"]:
        items = fetch_newsnow(src, hours=hours, limit=20)
        for it in items:
            it["category"] = "finance"
        out.extend(items)
    out.sort(key=lambda x: x["timestamp"], reverse=True)
    return out


def fetch_astock(hours: int = 6) -> List[Dict]:
    """A 股焦点: 雪球热股 + 财联社深度"""
    out = []
    for src in NEWSNOW_SOURCES["astock"]:
        items = fetch_newsnow(src, hours=hours, limit=15)
        for it in items:
            it["category"] = "astock"
        out.extend(items)
    out.sort(key=lambda x: x["timestamp"], reverse=True)
    return out


def fetch_global(hours: int = 12) -> List[Dict]:
    """全球宏观: Yahoo Finance / 36氪"""
    out = []
    for name, url in RSS_SOURCES["global"]:
        items = fetch_rss(name, url, hours=hours, limit=15)
        for it in items:
            it["category"] = "global"
        out.extend(items)
    out.sort(key=lambda x: x["timestamp"], reverse=True)
    return out


def fetch_all_categories(hours: int = 6) -> Dict[str, List[Dict]]:
    """一站式拉取 4 大分类

    Returns:
        {
            "policy":  [...],
            "finance": [...],
            "astock":  [...],
            "global":  [...],
        }
    """
    return {
        "policy":  fetch_policy(hours=max(hours, 12)),  # 政策类事件密度低，用更长窗口
        "finance": fetch_finance(hours=hours),
        "astock":  fetch_astock(hours=hours),
        "global":  fetch_global(hours=max(hours, 12)),
    }


if __name__ == "__main__":
    # CLI 快速体检
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=4)
    ap.add_argument("--category", default="all",
                    choices=["all", "policy", "finance", "astock", "global"])
    args = ap.parse_args()

    if args.category == "all":
        result = fetch_all_categories(hours=args.hours)
        for cat, items in result.items():
            print(f"\n=== {cat.upper()} ({len(items)} 条) ===")
            for it in items[:5]:
                print(f"  [{it['timestamp']}] ({it['source']}) {it['text'][:90]}")
    else:
        fn = {
            "policy":  fetch_policy,
            "finance": fetch_finance,
            "astock":  fetch_astock,
            "global":  fetch_global,
        }[args.category]
        items = fn(hours=args.hours)
        print(f"共 {len(items)} 条")
        for it in items[:20]:
            print(f"[{it['timestamp']}] ({it['source']}) {it['text'][:100]}")
