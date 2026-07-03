"""数据源"""
import urllib.request
import urllib.parse
import json
import re
import sys
from typing import List, Dict, Optional


DEFAULT_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


def http_get(url: str, encoding: str = "gbk", timeout: int = 15,
             headers: Optional[Dict] = None) -> str:
    h = DEFAULT_HEADERS.copy()
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    return urllib.request.urlopen(req, timeout=timeout).read().decode(encoding)


# ============ 新浪财经 ============

def sina_realtime(codes: List[str]) -> List[str]:
    """批量获取实时行情，返回原始 lines"""
    url = "http://hq.sinajs.cn/list=" + ",".join(codes)
    data = http_get(url)
    return data.strip().split("\n")


def parse_index_simple(line: str) -> Optional[Dict]:
    """解析 s_ 简易指数: 名称,现价,涨跌额,涨跌幅,成交量"""
    m = re.search(r'"([^"]+)"', line)
    if not m:
        return None
    parts = m.group(1).split(",")
    if len(parts) < 4:
        return None
    try:
        return {
            "name": parts[0],
            "close": float(parts[1]),
            "change": float(parts[2]),
            "pct": float(parts[3]),
        }
    except (ValueError, IndexError):
        return None


def parse_stock(line: str) -> Optional[Dict]:
    """解析 sh/sz 股票或 ETF: 名称,今开,昨收,现价,最高,最低..."""
    m = re.search(r'"([^"]+)"', line)
    if not m:
        return None
    parts = m.group(1).split(",")
    if len(parts) < 5:
        return None
    try:
        pre = float(parts[2]) if parts[2] else 0
        cur = float(parts[3]) if parts[3] else 0
        if cur == 0:
            cur = pre
        pct = (cur - pre) / pre * 100 if pre else 0
        return {"name": parts[0], "close": cur, "pre_close": pre, "pct": pct}
    except (ValueError, IndexError):
        return None


def parse_us_index(line: str) -> Optional[Dict]:
    """解析 int_ 美股指数: 名称,现价,涨跌额,涨跌幅"""
    return parse_index_simple(line)


def parse_us_stock(line: str) -> Optional[Dict]:
    """解析 gb_ 美股: 名称,现价,涨跌幅,时间..."""
    m = re.search(r'"([^"]+)"', line)
    if not m:
        return None
    parts = m.group(1).split(",")
    if len(parts) < 3:
        return None
    try:
        return {"name": parts[0], "close": float(parts[1]), "pct": float(parts[2])}
    except (ValueError, IndexError):
        return None


def parse_hk_index(line: str) -> Optional[Dict]:
    """港股指数: HSI,恒生指数,昨收,今开,最高,最低,现价,涨跌额,涨跌幅..."""
    m = re.search(r'"([^"]+)"', line)
    if not m:
        return None
    parts = m.group(1).split(",")
    if len(parts) < 10:
        return None
    try:
        pre = float(parts[3])
        cur = float(parts[6])
        if cur == 0:
            cur = pre
        return {
            "name": parts[1],
            "close": cur,
            "change": float(parts[7]),
            "pct": float(parts[8]),
            "pre_close": pre,
        }
    except (ValueError, IndexError):
        return None


def parse_hk_stock(line: str) -> Optional[Dict]:
    """港股股票: 名,英文名,今开,昨收,最高,最低,现价..."""
    m = re.search(r'"([^"]+)"', line)
    if not m:
        return None
    parts = m.group(1).split(",")
    if len(parts) < 10:
        return None
    try:
        pre = float(parts[3])
        cur = float(parts[6])
        if cur == 0:
            cur = pre
        pct = (cur - pre) / pre * 100 if pre else 0
        return {"name": parts[0], "close": cur, "pct": pct, "pre_close": pre}
    except (ValueError, IndexError):
        return None


def get_kline(symbol: str, days: int = 15, scale: int = 240) -> List[Dict]:
    """获取指数/ETF 日 K 线"""
    url = (
        f"http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&ma=5&datalen={days}"
    )
    try:
        raw = http_get(url, encoding="utf-8")
        # 补齐 JSON 引号
        raw = re.sub(r"(\w+):", r'"\1":', raw)
        return json.loads(raw)
    except Exception as e:
        print(f"[kline] {symbol} 错误: {e}", file=sys.stderr)
        return []


# ============ 东财板块 ============

def eastmoney_sectors(page_size: int = 30) -> List[Dict]:
    """获取东财板块涨跌"""
    url = (
        f"https://push2.eastmoney.com/api/qt/clist/get?"
        f"pn=1&pz={page_size}&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f3,f14"
    )
    try:
        raw = http_get(
            url, encoding="utf-8",
            headers={"Referer": "https://quote.eastmoney.com/"},
        )
        j = json.loads(raw)
        items = j.get("data", {}).get("diff", [])
        result = []
        for item in items:
            try:
                result.append({"name": item.get("f14"), "pct": float(item.get("f3"))})
            except (TypeError, ValueError):
                continue
        return result
    except Exception as e:
        print(f"[sectors] 错误: {e}", file=sys.stderr)
        return []
