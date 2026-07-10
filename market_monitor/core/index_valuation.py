"""
指数估值分位监控（W4 · Phase 1）

跟踪核心宽基/风格指数的 PE / PB / 股息率，计算当前值在历史里的分位，
分位极端时（≤P10 或 ≥P90）标注罕见信号。

数据源：
- akshare.stock_index_pe_lg / stock_index_pb_lg
  长历史 5000+ 天，但只覆盖：上证50、沪深300、上证380
- akshare.stock_zh_index_value_csindex
  覆盖广（红利/中证 500/中证 1000 等），但历史只有 20 天（滚动）
- akshare.stock_a_all_pb  全 A 中位数 PB，长历史，情绪辅助信号

设计：
- 双源冗余：LG 与 csindex 同一天同一指数都写入（source 字段区分）
- 分位窗口：3 年（≈750 交易日）为主展示，另算全历史作参考
- 极端阈值：P10 / P90 触发罕见信号

依赖 doc：docs/iterations/W4-valuation-screener.md
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================
# 常量 / 配置
# ============================================================

# 分位阈值（罕见 / 一般）
_EXTREME_LOW = 10.0      # ≤10% 分位 = 极便宜
_EXTREME_HIGH = 90.0     # ≥90% 分位 = 极贵
_CHEAP = 20.0
_EXPENSIVE = 80.0

# 分位窗口
_WINDOW_3Y_DAYS = 750    # 3 年 ≈ 750 交易日
_WINDOW_5Y_DAYS = 1250   # 5 年 ≈ 1250 交易日

_HIST_MIN_SAMPLES = 100  # 少于 100 样本不算分位

# 数据库
_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "market.db"


# ============================================================
# 覆盖清单
# ============================================================

# LG 源：长历史 5000+ 天，覆盖窄。symbol = akshare 用的名字
INDEX_LG = [
    ("上证50",  "sh000016"),
    ("沪深300", "sh000300"),
    ("上证380", "sh000009"),
]

# csindex 源：历史短（20 天滚动），覆盖广。symbol = 中证指数代码
INDEX_CSINDEX = [
    ("000015", "上证红利"),
    ("000016", "上证50"),
    ("000300", "沪深300"),
    ("000905", "中证500"),
    ("000852", "中证1000"),
]


# ============================================================
# 表初始化
# ============================================================

def _init_snapshot_table() -> None:
    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS index_valuation_snapshot (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                ts             DATETIME NOT NULL,
                trade_date     DATE     NOT NULL,
                symbol         TEXT     NOT NULL,
                name           TEXT,
                pe             REAL,
                pb             REAL,
                dividend_yield REAL,
                source         TEXT NOT NULL,
                UNIQUE(trade_date, symbol, source)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_index_val_symbol_date
                ON index_valuation_snapshot(symbol, trade_date)
        """)
        conn.commit()
    finally:
        conn.close()


# ============================================================
# 落库
# ============================================================

def _save_snapshot(rows: list[dict]) -> int:
    """把当日快照写入 index_valuation_snapshot；返回写入行数（已去重）"""
    if not rows:
        return 0
    _init_snapshot_table()
    conn = sqlite3.connect(_DB_PATH)
    try:
        cur = conn.executemany("""
            INSERT OR IGNORE INTO index_valuation_snapshot
              (ts, trade_date, symbol, name, pe, pb, dividend_yield, source)
            VALUES
              (:ts, :trade_date, :symbol, :name, :pe, :pb, :dy, :source)
        """, rows)
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()


# ============================================================
# 数据拉取：LG 源
# ============================================================

def _retry(fn, tries: int = 3, sleep_s: float = 1.0):
    """简易重试：LG 接口偶发返回 NoneType.attrs"""
    import time
    last_exc = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if i < tries - 1:
                time.sleep(sleep_s * (i + 1))
    raise last_exc if last_exc else RuntimeError("retry exhausted")


def _fetch_lg_pe(symbol_name: str) -> Optional[pd.DataFrame]:
    """akshare.stock_index_pe_lg(symbol='上证50'|'沪深300'|'上证380')

    返回列：日期、指数、等权静态市盈率、静态市盈率、静态市盈率中位数、
             等权滚动市盈率、滚动市盈率、滚动市盈率中位数
    """
    import akshare as ak
    try:
        df = _retry(lambda: ak.stock_index_pe_lg(symbol=symbol_name))
        df["日期"] = pd.to_datetime(df["日期"]).dt.date
        return df
    except Exception as e:
        logger.warning("[valuation] LG PE fetch fail: %s: %s", symbol_name, e)
        return None


def _fetch_lg_pb(symbol_name: str) -> Optional[pd.DataFrame]:
    """akshare.stock_index_pb_lg(symbol='上证50'|...)

    返回列：日期、指数、市净率、等权市净率、市净率中位数
    """
    import akshare as ak
    try:
        df = _retry(lambda: ak.stock_index_pb_lg(symbol=symbol_name))
        df["日期"] = pd.to_datetime(df["日期"]).dt.date
        return df
    except Exception as e:
        logger.warning("[valuation] LG PB fetch fail: %s: %s", symbol_name, e)
        return None


# ============================================================
# 数据拉取：csindex 源
# ============================================================

def _fetch_csindex(symbol: str) -> Optional[pd.DataFrame]:
    """akshare.stock_zh_index_value_csindex(symbol='000300')

    返回列：日期、指数代码、指数中文简称、市盈率1、市盈率2、股息率1、股息率2
    - 市盈率1 = 静态PE，市盈率2 = 滚动PE
    - 股息率1 = 近12个月，股息率2 = 近12个月加权
    """
    import akshare as ak
    try:
        df = ak.stock_zh_index_value_csindex(symbol=symbol)
        df["日期"] = pd.to_datetime(df["日期"]).dt.date
        return df
    except Exception as e:
        logger.warning("[valuation] csindex fetch fail: %s: %s", symbol, e)
        return None


# ============================================================
# 分位数计算
# ============================================================

def _percentile_of(values: pd.Series, current: float) -> Optional[float]:
    """返回 current 在 values 里的分位（百分比）；样本不够或值缺失返回 None"""
    if current is None or pd.isna(current):
        return None
    v = values.dropna()
    if len(v) < _HIST_MIN_SAMPLES:
        return None
    rank = (v < current).sum() + (v == current).sum() * 0.5
    return float(rank / len(v) * 100)


def _calc_percentiles_for_lg(df_pe: pd.DataFrame, df_pb: pd.DataFrame) -> dict:
    """给定 LG 返回的 PE、PB DataFrame，算最新值 + 分位

    优先用 3 年窗口分位；样本不足回退全历史。
    """
    result = {}
    latest_pe = df_pe.iloc[-1]
    latest_pb = df_pb.iloc[-1]

    result["日期"] = latest_pe["日期"]
    result["pe"] = float(latest_pe["滚动市盈率"])
    result["pb"] = float(latest_pb["市净率"])

    # PE 分位（3 年）
    df_pe_3y = df_pe.tail(_WINDOW_3Y_DAYS)
    result["pe_pct_3y"] = _percentile_of(df_pe_3y["滚动市盈率"], result["pe"])
    result["pe_pct_all"] = _percentile_of(df_pe["滚动市盈率"], result["pe"])

    # PB 分位
    df_pb_3y = df_pb.tail(_WINDOW_3Y_DAYS)
    result["pb_pct_3y"] = _percentile_of(df_pb_3y["市净率"], result["pb"])
    result["pb_pct_all"] = _percentile_of(df_pb["市净率"], result["pb"])

    return result


# ============================================================
# 主入口
# ============================================================

def fetch_and_snapshot() -> list[dict]:
    """拉取全部覆盖清单 → 落库 → 返回摘要（含分位）

    输出结构：
    [
      {"symbol": "sh000300", "name": "沪深300", "source": "lg",
       "pe": 13.78, "pb": 1.31,
       "pe_pct_3y": 55.2, "pe_pct_all": 12.4,
       "pb_pct_3y": 40.1, "pb_pct_all": 5.6,
       "dividend_yield": None,
       "date": date(2026, 7, 9)},
      ...
    ]
    """
    _init_snapshot_table()
    snapshot_rows: list[dict] = []
    now_utc = datetime.utcnow()

    # ── LG 源 ────────────────────────────────────────
    lg_records: list[dict] = []
    for name, symbol in INDEX_LG:
        df_pe = _fetch_lg_pe(name)
        df_pb = _fetch_lg_pb(name)
        if df_pe is None or df_pb is None:
            continue
        stat = _calc_percentiles_for_lg(df_pe, df_pb)
        rec = {
            "symbol": symbol,
            "name": name,
            "source": "lg",
            "date": stat["日期"],
            "pe": stat["pe"],
            "pb": stat["pb"],
            "dividend_yield": None,
            "pe_pct_3y": stat["pe_pct_3y"],
            "pe_pct_all": stat["pe_pct_all"],
            "pb_pct_3y": stat["pb_pct_3y"],
            "pb_pct_all": stat["pb_pct_all"],
        }
        lg_records.append(rec)
        snapshot_rows.append({
            "ts": now_utc,
            "trade_date": stat["日期"],
            "symbol": symbol,
            "name": name,
            "pe": stat["pe"],
            "pb": stat["pb"],
            "dy": None,
            "source": "lg",
        })

    # ── csindex 源 ────────────────────────────────────
    csi_records: list[dict] = []
    for symbol, name in INDEX_CSINDEX:
        df = _fetch_csindex(symbol)
        if df is None or df.empty:
            continue
        # 最新一天（df.iloc[0] 是最新）
        latest = df.iloc[0]
        try:
            pe = float(latest["市盈率2"])  # 滚动
        except (KeyError, TypeError, ValueError):
            pe = None
        try:
            dy = float(latest["股息率1"])
        except (KeyError, TypeError, ValueError):
            dy = None
        rec = {
            "symbol": symbol,
            "name": name,
            "source": "csindex",
            "date": latest["日期"],
            "pe": pe,
            "pb": None,
            "dividend_yield": dy,
            # csindex 只 20 天，无分位
            "pe_pct_3y": None,
            "pe_pct_all": None,
            "pb_pct_3y": None,
            "pb_pct_all": None,
        }
        csi_records.append(rec)
        snapshot_rows.append({
            "ts": now_utc,
            "trade_date": latest["日期"],
            "symbol": symbol,
            "name": name,
            "pe": pe,
            "pb": None,
            "dy": dy,
            "source": "csindex",
        })

    written = _save_snapshot(snapshot_rows)
    logger.info("[valuation] snapshot rows written=%d", written)

    return lg_records + csi_records


# ============================================================
# 交叉验证：LG vs csindex 同指数
# ============================================================

# 已知合理差异：LG「滚动PE」 vs csindex「市盈率2」加权口径不同。
# 只在差异极大（>30%）且日期一致时才算真的可疑。
_CROSS_CHECK_THRESHOLD_PCT = 30.0


def cross_check(records: list[dict]) -> list[dict]:
    """比对 LG 与 csindex 对同一指数的 PE 差异；差异 > 30% 且日期同天记为可疑

    注：LG 用「整体法滚动PE」，csindex「市盈率2」是市值加权 PE，口径本身有 10~25%
    差异是常态。用一个宽松阈值只捕获真正的数据脏（如某源缺失更新）。
    """
    warnings = []
    lg_map = {r["name"]: r for r in records if r["source"] == "lg" and r["pe"]}
    csi_map = {r["name"]: r for r in records if r["source"] == "csindex" and r["pe"]}
    for name, lg in lg_map.items():
        csi = csi_map.get(name)
        if not csi:
            continue
        # 日期不一致也不比较（可能 csindex 未更新）
        if lg["date"] != csi["date"]:
            continue
        diff_pct = abs(lg["pe"] - csi["pe"]) / max(lg["pe"], csi["pe"]) * 100
        if diff_pct > _CROSS_CHECK_THRESHOLD_PCT:
            warnings.append({
                "name": name,
                "lg_pe": lg["pe"],
                "csi_pe": csi["pe"],
                "diff_pct": diff_pct,
            })
    return warnings


# ============================================================
# 信号判定
# ============================================================

def get_signals(records: list[dict]) -> list[dict]:
    """从记录里提取极端信号（P10 / P90）；仅 LG 源有分位"""
    signals = []
    for r in records:
        if r["source"] != "lg":
            continue

        # PE 分位（3 年优先）
        pe_pct = r.get("pe_pct_3y") if r.get("pe_pct_3y") is not None else r.get("pe_pct_all")
        pb_pct = r.get("pb_pct_3y") if r.get("pb_pct_3y") is not None else r.get("pb_pct_all")

        tags = []
        if pe_pct is not None:
            if pe_pct <= _EXTREME_LOW:
                tags.append(("pe_low", pe_pct))
            elif pe_pct >= _EXTREME_HIGH:
                tags.append(("pe_high", pe_pct))
        if pb_pct is not None:
            if pb_pct <= _EXTREME_LOW:
                tags.append(("pb_low", pb_pct))
            elif pb_pct >= _EXTREME_HIGH:
                tags.append(("pb_high", pb_pct))

        if tags:
            signals.append({
                "name": r["name"],
                "symbol": r["symbol"],
                "pe": r["pe"],
                "pb": r["pb"],
                "pe_pct": pe_pct,
                "pb_pct": pb_pct,
                "tags": tags,
            })
    return signals


# ============================================================
# 展示层
# ============================================================

def _pct_label(pct: Optional[float]) -> str:
    if pct is None:
        return "  -  "
    if pct <= _EXTREME_LOW:
        return f"🟢 {pct:5.1f}%"
    elif pct <= _CHEAP:
        return f"🟢 {pct:5.1f}%"
    elif pct >= _EXTREME_HIGH:
        return f"🔴 {pct:5.1f}%"
    elif pct >= _EXPENSIVE:
        return f"🟡 {pct:5.1f}%"
    else:
        return f"⚪ {pct:5.1f}%"


def format_summary(records: list[dict]) -> str:
    """完整表格式汇总，含分位标签"""
    lines = ["【📊 指数估值分位快照】"]
    lines.append("─" * 62)
    lines.append(f"{'指数':<10} {'PE':>7} {'PE分位(3Y)':>13} {'PB':>7} {'PB分位(3Y)':>13}")

    for r in records:
        if r["source"] != "lg":
            continue
        pe = f"{r['pe']:.2f}" if r["pe"] else "  -  "
        pb = f"{r['pb']:.2f}" if r["pb"] else "  -  "
        pe_pct = _pct_label(r.get("pe_pct_3y"))
        pb_pct = _pct_label(r.get("pb_pct_3y"))
        lines.append(f"{r['name']:<10} {pe:>7} {pe_pct:>13} {pb:>7} {pb_pct:>13}")

    # csindex 广度补充（当前值，无分位）
    csi_lines = []
    for r in records:
        if r["source"] != "csindex":
            continue
        pe = f"{r['pe']:.2f}" if r["pe"] else "-"
        dy = f"{r['dividend_yield']:.2f}%" if r["dividend_yield"] else "-"
        csi_lines.append(f"  {r['name']:<10} PE={pe:>6}  股息率={dy}")

    if csi_lines:
        lines.append("")
        lines.append("─── 广度补充（无历史分位）───")
        lines.extend(csi_lines)

    return "\n".join(lines)


def format_signals(signals: list[dict], warnings: Optional[list[dict]] = None) -> str:
    """极端信号 + 数据一致性告警"""
    if not signals and not warnings:
        return ""
    lines = []
    if signals:
        lines.append("【⚠️ 指数估值极端信号（3 年分位）】")
        for s in signals:
            tag_str = " / ".join(f"{k}={v:.1f}%" for k, v in s["tags"])
            lines.append(f"  · {s['name']} PE={s['pe']:.2f} PB={s['pb']:.2f} → {tag_str}")
    if warnings:
        if lines:
            lines.append("")
        lines.append("【🔧 数据一致性告警】")
        for w in warnings:
            lines.append(
                f"  · {w['name']}: LG PE={w['lg_pe']:.2f} vs csindex PE={w['csi_pe']:.2f} "
                f"差异 {w['diff_pct']:.1f}%"
            )
    return "\n".join(lines)


__all__ = [
    "fetch_and_snapshot",
    "cross_check",
    "get_signals",
    "format_summary",
    "format_signals",
    "INDEX_LG",
    "INDEX_CSINDEX",
]
