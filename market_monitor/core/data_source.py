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


def _to_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def parse_a_index_full(line: str):
    """完整 A 股指数（含盘前逻辑）: 名称,今开,昨收,现价,最高,最低,..."""
    if "=" not in line:
        return None
    vals = line.split("=")[1].strip('";').split(",")
    if len(vals) < 4:
        return None
    name = vals[0]
    prev = _to_float(vals[2])
    cur = _to_float(vals[3])
    if cur > 0 and prev > 0:
        price = cur
        pct = (cur - prev) / prev * 100
        stage = "live"
    elif prev > 0:
        price = prev
        pct = 0.0
        stage = "pre"
    else:
        price = cur or prev
        pct = 0.0
        stage = "closed"
    amount = _to_float(vals[9]) if len(vals) > 9 else 0
    return {
        "name": name,
        "close": price,
        "price": price,  # alias
        "change_pct": pct,
        "pct": pct,  # alias
        "stage": stage,
        "amount": amount,
    }


def parse_us_v2(line: str):
    """美股 gb_ 格式（morning 用）: 名称,现价,涨跌%,时间,涨跌额,..."""
    if "=" not in line:
        return None
    vals = line.split("=")[1].strip('";').split(",")
    if len(vals) < 3:
        return None
    return {
        "name": vals[0],
        "price": _to_float(vals[1]),
        "close": _to_float(vals[1]),
        "change_pct": _to_float(vals[2]),
        "pct": _to_float(vals[2]),
    }


def parse_hk_index_full(line: str):
    """港股完整: HSI,恒生指数,昨收,今开,最高,最低,现价,涨跌,涨跌%,..."""
    if "=" not in line:
        return None
    vals = line.split("=")[1].strip('";').split(",")
    if len(vals) < 10:
        return None
    return {
        "name": vals[1],
        "price": _to_float(vals[6]),
        "close": _to_float(vals[6]),
        "change_pct": _to_float(vals[8]),
        "pct": _to_float(vals[8]),
    }


def parse_hf_commodity(line: str):
    """外盘商品 hf_: 现价,,买价,卖价,最高,最低,时间,昨结,今开,...,名称"""
    if "=" not in line:
        return None
    vals = line.split("=")[1].strip('";').split(",")
    if len(vals) < 8:
        return None
    price = _to_float(vals[0])
    prev = _to_float(vals[7], default=price)
    pct = (price - prev) / prev * 100 if prev else 0
    name = vals[13] if len(vals) > 13 else "商品"
    return {"name": name, "price": price, "close": price,
            "change_pct": pct, "pct": pct}


def parse_nf_futures(line: str):
    """内盘期货 nf_: 名称,时间,开盘,最高,最低,昨收,昨结,现价,最新,..."""
    if "=" not in line:
        return None
    vals = line.split("=")[1].strip('";').split(",")
    if len(vals) < 11:
        return None
    price = _to_float(vals[8])
    prev_settle = _to_float(vals[10], default=price)
    pct = (price - prev_settle) / prev_settle * 100 if prev_settle else 0
    return {"name": vals[0], "price": price, "close": price,
            "change_pct": pct, "pct": pct}


# ============ Yahoo Finance (VIX / 美债10Y) ============

def yahoo_quote(symbol: str, timeout: int = 8) -> Optional[Dict]:
    """从 Yahoo Finance 拉一个 quote。

    Args:
        symbol: Yahoo 代码，如 '^VIX', '^TNX', '^TYX'

    Returns:
        {'name', 'price', 'prev', 'pct'} 或 None
    """
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d"
    try:
        raw = http_get(url, encoding="utf-8", timeout=timeout,
                       headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.yahoo.com"})
        data = json.loads(raw)
        result = data.get("chart", {}).get("result") or []
        if not result:
            return None
        meta = result[0].get("meta", {})
        price = _to_float(meta.get("regularMarketPrice"))
        prev = _to_float(meta.get("chartPreviousClose"), default=price)
        if not price:
            return None
        pct = (price - prev) / prev * 100 if prev else 0
        return {
            "name": symbol,
            "price": price,
            "close": price,
            "prev": prev,
            "pct": pct,
            "change_pct": pct,
        }
    except Exception as e:
        print(f"[yahoo_quote] {symbol} error: {e}", file=sys.stderr)
        return None


def parse_dxy(line: str):
    """美元指数 DINIW: 时间,现价,买价,卖价,成交量,今开,最高,最低,昨收,名称,日期"""
    if "=" not in line:
        return None
    vals = line.split("=")[1].strip('";').split(",")
    if len(vals) < 9:
        return None
    price = _to_float(vals[1])
    prev = _to_float(vals[8], default=price)
    pct = (price - prev) / prev * 100 if prev else 0
    name = vals[9] if len(vals) > 9 else "美元指数"
    return {"name": name, "price": price, "close": price,
            "change_pct": pct, "pct": pct}


def sina_map(codes: List[str]) -> Dict[str, str]:
    """批量获取实时行情，返回 {code: line}"""
    lines = sina_realtime(codes)
    result = {}
    for line in lines:
        line = line.strip().rstrip(";")
        if not line or "=" not in line:
            continue
        key = line.split("=")[0].replace("var hq_str_", "").strip()
        result[key] = line
    return result


def get_top_movers(count: int = 5):
    """涨/跌幅榜 TOP N（新浪 A 股）"""
    result = ([], [])
    try:
        gainers_url = (
            "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"Market_Center.getHQNodeData?page=1&num=10&sort=changepercent&asc=0&node=hs_a"
        )
        losers_url = (
            "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
            f"Market_Center.getHQNodeData?page=1&num=10&sort=changepercent&asc=1&node=hs_a"
        )
        gainers = json.loads(http_get(gainers_url, encoding="utf-8"))
        losers = json.loads(http_get(losers_url, encoding="utf-8"))
        return gainers[:count], losers[:count]
    except Exception as e:
        print(f"[movers] 错误: {e}", file=sys.stderr)
        return result


def get_sector_hot(count: int = 5):
    """东财板块涨/跌幅榜 TOP N"""
    try:
        up_url = (
            "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=10&po=1&np=1"
            "&fltt=2&invt=2&fid=f3&fields=f2,f3,f4,f12,f14,f62&fs=m:90+t:2+f:!50"
        )
        dn_url = (
            "http://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=10&po=0&np=1"
            "&fltt=2&invt=2&fid=f3&fields=f2,f3,f4,f12,f14,f62&fs=m:90+t:2+f:!50"
        )
        h = {"Referer": "https://quote.eastmoney.com/"}
        up = json.loads(http_get(up_url, encoding="utf-8", headers=h))
        dn = json.loads(http_get(dn_url, encoding="utf-8", headers=h))
        return (
            up.get("data", {}).get("diff", [])[:count],
            dn.get("data", {}).get("diff", [])[:count],
        )
    except Exception as e:
        print(f"[sector_hot] 错误: {e}", file=sys.stderr)
        return [], []


def get_sina_quote(code: str):
    """单支股票/指数/ETF 实时数据（兼容 s_ 前缀和完整接口）"""
    try:
        lines = sina_realtime([code])
        if not lines:
            return None
        line = lines[0].strip().rstrip(";")
        if "=" not in line:
            return None
        vals = line.split("=")[1].strip('"').split(",")
        name = vals[0]
        if code.startswith("s_"):
            close = _to_float(vals[1])
            pct = _to_float(vals[3]) if len(vals) > 3 else 0
            amount = _to_float(vals[5]) if len(vals) > 5 else 0
            stage = "live" if close > 0 else "closed"
            return {"name": name, "close": close, "price": close,
                    "change_pct": pct, "pct": pct,
                    "amount": amount, "stage": stage}
        if len(vals) < 10:
            return None
        prev = _to_float(vals[2])
        cur = _to_float(vals[3])
        if cur > 0 and prev > 0:
            close = cur
            pct = (cur - prev) / prev * 100
            stage = "live"
        elif prev > 0:
            close = prev
            pct = 0.0
            stage = "pre"
        else:
            close = cur or prev
            pct = 0.0
            stage = "closed"
        amount = _to_float(vals[9]) if len(vals) > 9 else 0
        return {"name": name, "close": close, "price": close,
                "change_pct": pct, "pct": pct,
                "amount": amount, "stage": stage}
    except Exception as e:
        print(f"[quote] {code} 失败: {e}", file=sys.stderr)
        return None


def calc_week_change(symbol: str):
    """周累计涨跌幅（基于日 K）"""
    from datetime import datetime
    kline = get_kline(symbol, days=10)
    if len(kline) < 2:
        return None
    try:
        today = kline[-1]
        today_date = datetime.strptime(today["day"], "%Y-%m-%d")
        weekday = today_date.weekday()  # 0=Mon
        base_close = None
        for k in reversed(kline[:-1]):
            d = datetime.strptime(k["day"], "%Y-%m-%d")
            if d < today_date and d.weekday() == 4:
                base_close = float(k["close"])
                break
        if base_close is None:
            idx = min(weekday + 1, len(kline) - 1)
            base_close = float(kline[-(idx + 1)]["close"])
        today_close = float(today["close"])
        return (today_close - base_close) / base_close * 100
    except Exception as e:
        print(f"[week_change] {symbol} 失败: {e}", file=sys.stderr)
        return None
