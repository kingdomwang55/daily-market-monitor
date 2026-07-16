"""U.S. Treasury 官方收益率曲线（DS-1）

- 数据源：https://home.treasury.gov/resource-center/data-chart-center/interest-rates/
- 免费、无 Key、日频、官方权威
- 相比 Yahoo Finance ^TNX/^FVX/^TYX：**多了 2Y、3Y、7Y、20Y**，正好补齐 2Y-10Y 衰退指标

依赖 doc：docs/iterations/DS1-us-treasury.md
"""
from __future__ import annotations

import csv
import io
import logging
import time
import urllib.request
from datetime import date, datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 常量
# ============================================================

_CSV_URL_TMPL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all"
    "?type=daily_treasury_yield_curve&field_tdr_date_value={year}&_format=csv"
)

# CSV 列名 → 内部 key
_COL_MAP = {
    "1 Mo": "1M", "3 Mo": "3M", "6 Mo": "6M",
    "1 Yr": "1Y", "2 Yr": "2Y", "3 Yr": "3Y",
    "5 Yr": "5Y", "7 Yr": "7Y", "10 Yr": "10Y",
    "20 Yr": "20Y", "30 Yr": "30Y",
}

_HEADERS = {
    "User-Agent": "market-monitor/1.0 (https://github.com/user/market-monitor; contact: local)",
}

_TIMEOUT_S = 10
_RETRIES = 2

# 内存缓存：{year: (fetched_at_ts, dataframe_like_list_of_dicts)}
_CACHE: dict[int, tuple[float, list[dict]]] = {}
_CACHE_TTL_S = 3600  # 1 小时


# ============================================================
# CSV 拉取（带缓存）
# ============================================================

def _fetch_year_csv(year: int) -> Optional[list[dict]]:
    """拉取指定年份 CSV，解析为 [{date, 2Y, 10Y, ...}] 列表（按日期升序）"""
    now = time.time()
    cached = _CACHE.get(year)
    if cached and (now - cached[0] < _CACHE_TTL_S):
        return cached[1]

    url = _CSV_URL_TMPL.format(year=year)
    last_exc = None
    for i in range(_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
                text = resp.read().decode("utf-8")
            reader = csv.DictReader(io.StringIO(text))
            rows: list[dict] = []
            for row in reader:
                d_str = row.get("Date", "")
                try:
                    d = datetime.strptime(d_str, "%m/%d/%Y").date()
                except ValueError:
                    continue
                out = {"date": d}
                for csv_col, key in _COL_MAP.items():
                    v = row.get(csv_col, "").strip()
                    if v:
                        try:
                            out[key] = float(v)
                        except ValueError:
                            pass
                rows.append(out)
            # 按日期升序
            rows.sort(key=lambda x: x["date"])
            _CACHE[year] = (now, rows)
            return rows
        except Exception as e:
            last_exc = e
            if i < _RETRIES:
                time.sleep(1.0 * (i + 1))

    logger.warning("[us_treasury] fetch year=%d fail: %s", year, last_exc)
    return None


# ============================================================
# 公共 API
# ============================================================

def fetch_yield_curve() -> Optional[dict]:
    """获取最新一日全收益率曲线。

    返回：
      {
        "date": date(2026, 7, 9),
        "source": "us_treasury",
        "1M": 3.72, "3M": 3.83, ..., "2Y": 4.16, ..., "30Y": 5.05
      }
    失败返回 None。
    """
    year = datetime.utcnow().year
    rows = _fetch_year_csv(year)
    if not rows:
        # 元旦附近 fallback 上一年
        rows = _fetch_year_csv(year - 1)
    if not rows:
        return None
    latest = rows[-1]
    result = {"source": "us_treasury"}
    result.update(latest)
    return result


def get_key_spreads(curve: dict) -> dict:
    """计算关键利差（bp = 基点）"""
    if not curve:
        return {}
    y2 = curve.get("2Y")
    y10 = curve.get("10Y")
    y30 = curve.get("30Y")
    y5 = curve.get("5Y")
    m3 = curve.get("3M")

    out: dict = {}
    if y2 is not None and y10 is not None:
        out["2Y-10Y"] = round((y10 - y2) * 100, 1)
        out["inverted_2y10y"] = y10 < y2
    if m3 is not None and y10 is not None:
        out["3M-10Y"] = round((y10 - m3) * 100, 1)
        out["inverted_3m10y"] = y10 < m3
    if y5 is not None and y30 is not None:
        out["5Y-30Y"] = round((y30 - y5) * 100, 1)
    return out


def get_curve_with_changes(days_back: int = 1) -> Optional[dict]:
    """在 `fetch_yield_curve()` 基础上，附加与 N 天前的变化（bp）"""
    year = datetime.utcnow().year
    rows = _fetch_year_csv(year)
    if not rows or len(rows) < days_back + 1:
        # 跨年 fallback
        prev_rows = _fetch_year_csv(year - 1) or []
        rows = prev_rows + (rows or [])
    if not rows:
        return None

    latest = rows[-1]
    if len(rows) > days_back:
        prev = rows[-1 - days_back]
    else:
        prev = None

    out = {"source": "us_treasury"}
    out.update(latest)
    if prev:
        changes = {}
        for k in _COL_MAP.values():
            if k in latest and k in prev:
                changes[k] = round((latest[k] - prev[k]) * 100, 1)  # bp
        out["changes_bp"] = changes
        out["prev_date"] = prev["date"]
    return out


__all__ = ["fetch_yield_curve", "get_key_spreads", "get_curve_with_changes"]
