"""Bloomberg 发文言论数据源

三管齐下：
1. 🏛️ Markets RSS（最核心，覆盖市场/宏观/个股报道）
2. 🏛️ Politics RSS（政策/关税/地缘政治）
3. 🏛️ Technology RSS（科技/AI/半导体）
4. 🏛️ Economics RSS（经济数据/央行政策）
5. 📰 Google News 补充（Opinion 观点文章 + 模糊查询）

Bloomberg 的 RSS 直接访问无需鉴权，GFW 下可能需要代理。
每条输出统一格式（与 news_sources 对齐）：
{
    "id": "唯一hash",
    "category": "markets/politics/tech/economics/opinion",
    "source": "bloomberg-markets/bloomberg-politics/bloomberg-tech/bloomberg-econ/googlenews",
    "timestamp": "2026-07-22 16:44",
    "text": "文章标题",
    "summary": "文章摘要/首段",
    "link": "原文链接",
    "author": "作者名",
}
"""
import hashlib
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Dict, Optional

import ssl

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

CN_TZ = timezone(timedelta(hours=8))

# Bloomberg RSS 源（按优先顺序排列）
BLOOMBERG_RSS = [
    # (category, source_name, url)
    ("markets", "bloomberg-markets", "https://feeds.bloomberg.com/markets/news.rss"),
    ("politics", "bloomberg-politics", "https://feeds.bloomberg.com/politics/news.rss"),
    ("tech", "bloomberg-tech", "https://feeds.bloomberg.com/technology/news.rss"),
    ("economics", "bloomberg-econ", "https://feeds.bloomberg.com/economics/news.rss"),
]

CATEGORY_LABELS = {
    "markets":   "🏛️ 市场",
    "politics":  "🏛️ 政策/地缘",
    "tech":      "🏛️ 科技",
    "economics": "🏛️ 经济/央行",
    "opinion":   "📰 观点/分析",
}


def _fetch(url: str, timeout: int = 10) -> Optional[bytes]:
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers=HEADERS)
        return urllib.request.urlopen(req, timeout=timeout, context=ctx).read()
    except Exception as e:
        print(f"[bloomberg_sources] fetch failed: {url[:80]} -> {e}", file=sys.stderr)
        return None


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _hash_id(source: str, link: str, text: str) -> str:
    key = f"{source}|{link}|{text[:100]}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


def _ts_from_rss_date(s: str) -> Optional[datetime]:
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(CN_TZ)
    except Exception:
        return None


def _ts_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


# ============ Bloomberg RSS ============

def fetch_bloomberg_rss(category: str, source_name: str, url: str,
                        hours: int = 24, limit: int = 30) -> List[Dict]:
    """拉取单个 Bloomberg RSS 源"""
    raw = _fetch(url, timeout=10)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"[fetch_bloomberg_rss] {source_name} parse error: {e}", file=sys.stderr)
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
        author = _clean_html(item.findtext("{http://purl.org/dc/elements/1.1/}creator") or "")
        text = title if title else desc
        if not text:
            continue

        if not dt_cn:
            dt_cn = datetime.now(CN_TZ)

        out.append({
            "id": _hash_id(source_name, link, text),
            "category": category,
            "source": source_name,
            "timestamp": _ts_str(dt_cn),
            "text": text,
            "summary": desc[:200] if desc else "",
            "link": link,
            "author": author,
        })
    return out[:limit]


def fetch_all_rss(hours: int = 24, limit_per_feed: int = 30) -> List[Dict]:
    """拉取所有 Bloomberg RSS 源"""
    all_items = []
    for category, source_name, url in BLOOMBERG_RSS:
        items = fetch_bloomberg_rss(category, source_name, url,
                                    hours=hours, limit=limit_per_feed)
        all_items.extend(items)
        print(f"[bloomberg_sources] {source_name}: {len(items)} 条", file=sys.stderr)
    # 按时间倒序
    all_items.sort(key=lambda x: x["timestamp"], reverse=True)
    return all_items


# ============ Google News 补充（Opinion/分析类） ============

def fetch_opinion_google_news(hours: int = 48, limit: int = 15) -> List[Dict]:
    """从 Google News 补充 Bloomberg 的观点/分析文章"""
    from urllib.parse import quote
    q = quote("site:bloomberg.com opinion")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    raw = _fetch(url)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"[bloomberg_sources] google news opinion parse error: {e}", file=sys.stderr)
        return []

    cutoff = datetime.now(CN_TZ) - timedelta(hours=hours)
    out = []
    seen = set()
    for item in root.findall(".//item")[:limit * 2]:
        pub_raw = (item.findtext("pubDate") or "").strip()
        try:
            dt = parsedate_to_datetime(pub_raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_cn = dt.astimezone(CN_TZ)
            if dt_cn < cutoff:
                continue
        except Exception:
            dt_cn = datetime.now(CN_TZ)

        title = _clean_html(item.findtext("title") or "")
        link = (item.findtext("link") or "").strip()
        if not title:
            continue

        # 去重：同一标题不重复
        dedup_key = hashlib.md5(title.lower().encode()).hexdigest()[:16]
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Google News 标题格式："xxx - Bloomberg", 去掉尾部来源
        source_media = ""
        if " - " in title:
            parts = title.rsplit(" - ", 1)
            title = parts[0]
            source_media = parts[1]

        # 只保留 bloomberg 的
        if "bloomberg" not in source_media.lower():
            continue

        out.append({
            "id": _hash_id("googlenews-opinion", link, title),
            "category": "opinion",
            "source": "googlenews-opinion",
            "timestamp": _ts_str(dt_cn),
            "text": title,
            "summary": "",
            "link": link,
            "author": "",
        })
    return out[:limit]


# ============ 汇总入口 ============

def fetch_all(hours: int = 24, include_opinion: bool = True) -> List[Dict]:
    """一站式拉取 Bloomberg 所有文章

    Args:
        hours: 回溯小时数
        include_opinion: 是否包含 Google News 补充的 opinion 文章

    Returns:
        时间倒序的去重文章列表
    """
    seen = set()
    out = []

    # 1. RSS 源
    rss_items = fetch_all_rss(hours=hours)
    for it in rss_items:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        out.append(it)

    # 2. Google News opinion 补充
    if include_opinion:
        opinion_items = fetch_opinion_google_news(hours=hours * 2, limit=15)
        for it in opinion_items:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            out.append(it)

    # 按时间倒序
    out.sort(key=lambda x: x["timestamp"], reverse=True)
    return out


def fetch_by_category(hours: int = 24) -> Dict[str, List[Dict]]:
    """按分类返回，方便 AI 分段处理"""
    all_items = fetch_all(hours=hours, include_opinion=True)
    result = {}
    for cat, label in CATEGORY_LABELS.items():
        result[cat] = [it for it in all_items if it["category"] == cat]
    return result


if __name__ == "__main__":
    # CLI 快速测试
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--category", default="all",
                    choices=["all"] + list(CATEGORY_LABELS.keys()))
    args = ap.parse_args()

    if args.category == "all":
        items = fetch_all(hours=args.hours)
        print(f"共 {len(items)} 条")
        for it in items[:10]:
            cat_label = CATEGORY_LABELS.get(it["category"], it["category"])
            print(f"[{it['timestamp']}] ({it['source']}) {cat_label}")
            print(f"  {it['text'][:100]}")
            if it.get("author"):
                print(f"  👤 {it['author']}")
            print()
    else:
        by_cat = fetch_by_category(hours=args.hours)
        items = by_cat.get(args.category, [])
        print(f"{args.category}: {len(items)} 条")
        for it in items[:10]:
            print(f"[{it['timestamp']}] ({it['source']}) {it['text'][:120]}")