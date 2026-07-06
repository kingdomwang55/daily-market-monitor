"""意见领袖发言数据源

三合一取数模块：
- Trump: trumpstruth.org RSS（Truth Social 第三方镜像）
- Musk: Nitter RSS（X 免代理镜像，多实例故障转移）
- Jensen / Altman / Dario: Google News RSS

每条发言输出统一格式：
{
    "id": "唯一hash",
    "person": "trump/musk/jensen",
    "source": "trumpstruth/nitter/googlenews",
    "timestamp": "2026-07-06 03:08",  # 尽量本地化
    "text": "发言正文",
    "link": "原文链接",
}
"""
import hashlib
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from typing import List, Dict, Optional


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

# Nitter 备用实例（首个失败自动切换；目前 Nitter 生态不稳定，多数会失败）
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://xcancel.com",
    "https://nitter.poast.org",
    "https://nitter.tiekoetter.com",
    "https://nitter.space",
]

CN_TZ = timezone(timedelta(hours=8))


def _fetch(url: str, timeout: int = 10) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        return urllib.request.urlopen(req, timeout=timeout).read()
    except Exception as e:
        print(f"[voice_sources] fetch failed: {url[:80]} -> {e}", file=sys.stderr)
        return None


def _clean_html(text: str) -> str:
    """去 HTML 标签 + 多余空白"""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_rss_date(s: str) -> str:
    """RSS pubDate → 北京时间字符串"""
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_cn = dt.astimezone(CN_TZ)
        return dt_cn.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return s[:16]


def _hash_id(person: str, link: str, text: str) -> str:
    """唯一 hash，去重用"""
    key = f"{person}|{link}|{text[:100]}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


# ============ Trump: trumpstruth.org ============

def fetch_trump(hours: int = 24) -> List[Dict]:
    """拉 Trump 最近 hours 小时的 Truth Social 发言"""
    raw = _fetch("https://trumpstruth.org/feed/")
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"[fetch_trump] parse error: {e}", file=sys.stderr)
        return []

    cutoff = datetime.now(CN_TZ) - timedelta(hours=hours)
    out = []
    for item in root.findall(".//item"):
        pub_raw = (item.findtext("pubDate") or "").strip()
        try:
            dt = parsedate_to_datetime(pub_raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_cn = dt.astimezone(CN_TZ)
            if dt_cn < cutoff:
                continue
        except Exception:
            continue

        title = (item.findtext("title") or "").strip()
        desc = _clean_html(item.findtext("description") or "")
        link = (item.findtext("link") or "").strip()
        text = desc if len(desc) > len(title) else title
        if not text:
            continue

        out.append({
            "id": _hash_id("trump", link, text),
            "person": "trump",
            "source": "trumpstruth",
            "timestamp": dt_cn.strftime("%Y-%m-%d %H:%M"),
            "text": text,
            "link": link,
        })
    return out


# ============ Musk: Nitter ============

def fetch_musk(hours: int = 24) -> List[Dict]:
    """拉 Musk 最近 hours 小时的 X 发言（含转推）"""
    for inst in NITTER_INSTANCES:
        url = f"{inst}/elonmusk/rss"
        raw = _fetch(url, timeout=8)
        if not raw:
            continue
        # xcancel 类返回 whitelist 提示页
        if b"whitelist" in raw[:2000].lower():
            continue
        try:
            root = ET.fromstring(raw)
        except Exception:
            continue

        items = root.findall(".//item")
        if not items:
            continue

        cutoff = datetime.now(CN_TZ) - timedelta(hours=hours)
        out = []
        for item in items:
            pub_raw = (item.findtext("pubDate") or "").strip()
            try:
                dt = parsedate_to_datetime(pub_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                dt_cn = dt.astimezone(CN_TZ)
                if dt_cn < cutoff:
                    continue
            except Exception:
                continue

            title = (item.findtext("title") or "").strip()
            desc = _clean_html(item.findtext("description") or "")
            link = (item.findtext("link") or "").strip()
            text = desc if len(desc) > len(title) else title
            if not text or text.startswith("R to @"):
                # 短回复噪音过多，跳过
                if len(text) < 40:
                    continue

            out.append({
                "id": _hash_id("musk", link, text),
                "person": "musk",
                "source": f"nitter({inst.replace('https://', '')})",
                "timestamp": dt_cn.strftime("%Y-%m-%d %H:%M"),
                "text": text,
                "link": link,
            })
        if out:
            return out

    # 回退：Google News RSS
    print("[fetch_musk] Nitter all failed, fallback to Google News", file=sys.stderr)
    return fetch_google_news(
        "musk",
        '"Elon Musk" says OR tweets OR announces OR posts',
        hours=hours,
    )


# ============ Google News RSS 通用 ============

def fetch_google_news(person: str, query: str, hours: int = 24,
                      limit: int = 20) -> List[Dict]:
    """通用 Google News RSS 拉取（Jensen/Altman/Dario 等）"""
    from urllib.parse import quote
    q = quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    raw = _fetch(url)
    if not raw:
        return []
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"[fetch_google_news] parse error: {e}", file=sys.stderr)
        return []

    cutoff = datetime.now(CN_TZ) - timedelta(hours=hours)
    out = []
    for item in root.findall(".//item")[:limit]:
        pub_raw = (item.findtext("pubDate") or "").strip()
        try:
            dt = parsedate_to_datetime(pub_raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt_cn = dt.astimezone(CN_TZ)
            if dt_cn < cutoff:
                continue
        except Exception:
            continue

        title = _clean_html(item.findtext("title") or "")
        desc = _clean_html(item.findtext("description") or "")
        link = (item.findtext("link") or "").strip()
        text = title
        if not text:
            continue

        # Google News 标题格式："xxx - Source Media"
        source_media = ""
        if " - " in title:
            parts = title.rsplit(" - ", 1)
            text = parts[0]
            source_media = parts[1]

        out.append({
            "id": _hash_id(person, link, text),
            "person": person,
            "source": f"googlenews({source_media})" if source_media else "googlenews",
            "timestamp": dt_cn.strftime("%Y-%m-%d %H:%M"),
            "text": text,
            "link": link,
        })
    return out


def fetch_jensen(hours: int = 24) -> List[Dict]:
    """黄仁勋（Nvidia CEO）"""
    return fetch_google_news("jensen", '"Jensen Huang"', hours)


def fetch_altman(hours: int = 24) -> List[Dict]:
    """Sam Altman（OpenAI CEO）"""
    return fetch_google_news("altman", '"Sam Altman"', hours)


def fetch_dario(hours: int = 24) -> List[Dict]:
    """Dario Amodei（Anthropic CEO）"""
    return fetch_google_news("dario", '"Dario Amodei"', hours)


# ============ 汇总入口 ============

VOICE_FETCHERS = {
    "trump": fetch_trump,
    "musk": fetch_musk,
    "jensen": fetch_jensen,
    "altman": fetch_altman,
    "dario": fetch_dario,
}


def fetch_all(persons: List[str], hours: int = 24) -> List[Dict]:
    """按人物列表拉取，返回合并去重后的时间倒序列表"""
    seen = set()
    out = []
    for p in persons:
        fn = VOICE_FETCHERS.get(p)
        if not fn:
            print(f"[fetch_all] unknown person: {p}", file=sys.stderr)
            continue
        try:
            items = fn(hours=hours)
        except Exception as e:
            print(f"[fetch_all] {p} error: {e}", file=sys.stderr)
            continue
        for it in items:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            out.append(it)

    # 按时间倒序
    out.sort(key=lambda x: x["timestamp"], reverse=True)
    return out


if __name__ == "__main__":
    # CLI 快速测试
    import json
    persons = sys.argv[1:] or ["trump", "musk", "jensen"]
    items = fetch_all(persons, hours=24)
    print(f"共 {len(items)} 条")
    for it in items[:5]:
        print(f"\n[{it['timestamp']}] {it['person']} ({it['source']})")
        print(f"  {it['text'][:150]}")
