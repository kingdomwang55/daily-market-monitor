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
    lines = data.strip().split("\n")
    # 新增：后台落库（异常不影响主流程）
    try:
        _save_realtime_snapshots(codes, lines)
    except Exception as e:
        print(f"[sina_realtime] 快照落库失败忽略: {e}", file=sys.stderr)
    return lines


def _save_realtime_snapshots(codes: List[str], lines: List[str]) -> None:
    """将 sina_realtime 的结果以快照形式落库

    需要区分不同类型（指数 / 股票 / 港股），根据 code 前缀判定：
    - s_开头 → parse_index_simple
    - hk开头 且后续为字母多 → hk_index / hk_stock 区分（一律用 parse_hk_index，注释里说明）
    - 其他 → skip（先覆盖 sina 主要 code，其他后续扩展）
    """
    # 延迟导入避免循环依赖
    try:
        from ..data.database import get_session
        from ..data.repositories import MarketSnapshotRepository
    except Exception:
        return  # 数据层不可用直接跳过

    rows = []
    for code, line in zip(codes, lines):
        info = None
        if code.startswith("s_"):
            info = parse_index_simple(line)
            stage = None
        elif code.startswith("hkH"):
            info = parse_hk_index(line)
            stage = None
        elif code.startswith("hk") and len(code) > 2 and code[2:].isdigit():
            info = parse_hk_stock(line)
            stage = None
        else:
            continue

        if not info:
            continue

        rows.append({
            "symbol": code,
            "price": info.get("close"),
            "prev_close": info.get("pre_close"),
            "pct": info.get("pct"),
            "stage": stage,
            "source": "sina",
            "raw": {"name": info.get("name")},
        })

    if not rows:
        return

    with get_session() as s:
        MarketSnapshotRepository(s).bulk_create(rows)


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
    """解析美股指数。

    兼容两种数据源：
    - int_ 简易接口：名称,现价,涨跌额,涨跌幅（仅收盘静态，无高低点）
    - gb_$ 完整接口：名称,现价,涨跌幅,时间,涨跌额,今开,最高,最低,...（含盘中高低点）

    自动探测字段数量：>= 8 字段视为 gb_$ 完整格式，解析出 high/low/open。
    """
    m = re.search(r'"([^"]+)"', line)
    if not m:
        return None
    parts = m.group(1).split(",")
    # gb_$ 完整格式：至少 8 个字段，含高低点
    if len(parts) >= 8:
        try:
            return {
                "name": parts[0],
                "close": float(parts[1]),
                "pct": float(parts[2]),
                "change": float(parts[4]) if parts[4] else None,
                "open": float(parts[5]) if parts[5] else None,
                "high": float(parts[6]) if parts[6] else None,
                "low": float(parts[7]) if parts[7] else None,
            }
        except (ValueError, IndexError):
            pass
    # 降级：int_ 简易格式
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


# ============ 沪深港通资金流（东方财富）============
# 港交所 2024-08 起停止公布北向实时净流入，仅保留成交额
# 南向数据仍完整（净流入、买入、卖出、成交额）

STOCK_CONNECT_URL = (
    "https://datacenter-web.eastmoney.com/api/data/v1/get"
    "?sortColumns=TRADE_DATE&sortTypes=-1&pageSize=60&pageNumber=1"
    "&reportName=RPT_MUTUAL_DEAL_HISTORY&columns=ALL&source=WEB&client=WEB"
)
STOCK_CONNECT_HEADERS = {
    "Referer": "https://data.eastmoney.com/",
    "User-Agent": "Mozilla/5.0",
}

# MUTUAL_TYPE 映射
_MUTUAL_TYPE_MAP = {
    "001": ("north_sh", "北向沪股通"),
    "003": ("north_sz", "北向深股通"),
    "005": ("north_total", "北向汇总"),
    "002": ("south_sh", "南向沪港通"),
    "004": ("south_sz", "南向深港通"),
    "006": ("south_total", "南向汇总"),
}


def fetch_stock_connect_history(days: int = 10) -> Dict[str, list]:
    """拉取沪深港通近 N 日资金流历史。

    返回结构：
    {
        "north_total": [{date, net, buy, sell, deal}, ...],  # 北向汇总（net 通常为 None）
        "south_total": [{date, net, buy, sell, deal}, ...],  # 南向汇总
        "north_sh": [...], "north_sz": [...],
        "south_sh": [...], "south_sz": [...],
    }
    每类按日期倒序（最近日在前）。
    单位：亿元。
    """
    try:
        req = urllib.request.Request(STOCK_CONNECT_URL, headers=STOCK_CONNECT_HEADERS)
        raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
        payload = json.loads(raw)
    except Exception as e:
        print(f"[stock_connect] 请求失败: {e}", file=sys.stderr)
        return {}

    rows = ((payload.get("result") or {}).get("data")) or []
    grouped: Dict[str, list] = {v[0]: [] for v in _MUTUAL_TYPE_MAP.values()}

    for row in rows:
        mt = row.get("MUTUAL_TYPE")
        key_pair = _MUTUAL_TYPE_MAP.get(mt)
        if not key_pair:
            continue
        key = key_pair[0]
        date = (row.get("TRADE_DATE") or "")[:10]

        def _to_yi(v):
            # 东财接口返回百万元，需除 100 转为亿元
            if v is None:
                return None
            try:
                return round(float(v) / 100.0, 2)
            except (TypeError, ValueError):
                return None

        item = {
            "date": date,
            "net": _to_yi(row.get("NET_DEAL_AMT")),
            "buy": _to_yi(row.get("BUY_AMT")),
            "sell": _to_yi(row.get("SELL_AMT")),
            "deal": _to_yi(row.get("DEAL_AMT")),
        }
        grouped[key].append(item)

    # 每类截取近 N 日（数据本身已按日期倒序）
    for k in grouped:
        grouped[k] = grouped[k][:days]
    return grouped


def fetch_south_flow_latest() -> Optional[Dict]:
    """获取最近一个交易日的南向汇总资金流。

    返回 {date, net, buy, sell, deal}，单位亿元。
    net = 净买入（正=资金南下抄底港股 / 负=撤离港股）
    """
    hist = fetch_stock_connect_history(days=2)
    south = hist.get("south_total") or []
    if not south:
        return None
    return south[0]


def fetch_south_flow_trend(days: int = 5) -> list:
    """获取近 N 个交易日南向汇总资金流序列（时间正序：最早在前）。"""
    hist = fetch_stock_connect_history(days=days)
    south = hist.get("south_total") or []
    # 反转为正序
    return list(reversed(south))


def fetch_north_deal_latest() -> Optional[Dict]:
    """获取最近一个交易日的北向汇总成交额（净买入不再公布）。

    返回 {date, deal}，单位亿元。
    """
    hist = fetch_stock_connect_history(days=2)
    north = hist.get("north_total") or []
    if not north:
        return None
    row = north[0]
    return {"date": row["date"], "deal": row["deal"]}
