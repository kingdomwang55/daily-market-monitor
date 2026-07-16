"""
烟蒂股筛选器（W4 · Phase 2）

从「已知低估值池」（默认上证红利指数 000015 的 50 只成分股）里
逐只查估值和 ROE，筛选深度价值股。

硬门槛（同时满足）：
  - PB < 0.7             （破净）
  - PE(TTM) < 10         （10 倍以下）
  - 累计分红次数 ≥ 5     （稳定分红习惯代理指标；股息率精确源不稳定）
  - 3 年年报 ROE 均值 > 0（稳定盈利，避免"低估值陷阱"）

评分（0-100）：股息能力、PB、ROE、PE、市值 五维加权。

数据源：
  - akshare.index_stock_cons_csindex(symbol='000015')  → 候选池
  - akshare.stock_value_em(symbol=...)                 → PE/PB/市值（最新日线）
  - akshare.stock_financial_analysis_indicator(...)    → 3 年 ROE
  - akshare.stock_history_dividend()                   → 累计分红次数 + 累计股息

依赖 doc：docs/iterations/W4-phase2-cigar-butt.md
"""

from __future__ import annotations

import logging
import sqlite3
import time
from datetime import datetime, date
from typing import Optional

import pandas as pd

from .db_path import ensure_sqlite_parent, sqlite_db_path

logger = logging.getLogger(__name__)


# ============================================================
# 常量 / 阈值
# ============================================================

# 硬门槛
_MAX_PB = 0.7
_MAX_PE = 10.0
_MIN_DIVIDEND_COUNT = 5           # 累计分红次数 ≥ 5
_MIN_ROE_3Y_AVG = 0.0             # 3 年 ROE 均值 > 0

# 罕见 / 提示
_EXTREME_LOW_PB = 0.4              # PB<0.4 极端破净警示

# 抓数据 rate limit
_SLEEP_BETWEEN_STOCKS = 0.4        # 秒
_RETRY_TIMES = 2

# 数据库
_DB_PATH = sqlite_db_path()

# 银行股白名单（行业属性特殊，PB<0.4 非退市风险）
_BANK_SYMBOLS = {
    "600015", "600016", "600036", "600908", "600919", "600926", "600928",
    "601009", "601077", "601128", "601166", "601169", "601229", "601288",
    "601328", "601398", "601528", "601577", "601658", "601818", "601825",
    "601838", "601860", "601916", "601939", "601963", "601988", "601997",
    "601998", "600000", "002142", "002807", "002839", "002936", "002948",
    "002958", "002966", "002985", "003006", "003009",
}
POOLS = {
    "sse_dividend": {
        "index_code": "000015",
        "name": "上证红利指数",
    },
    # 可后续加：中证红利 000922、深证红利 399324 等
}


# ============================================================
# 表初始化
# ============================================================

def _init_table() -> None:
    ensure_sqlite_parent(_DB_PATH)
    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cigar_butt_screening (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                run_ts         DATETIME NOT NULL,
                run_date       DATE     NOT NULL,
                pool           TEXT     NOT NULL,
                symbol         TEXT     NOT NULL,
                name           TEXT,
                pb             REAL,
                pe             REAL,
                dividend_count INTEGER,
                annual_dividend REAL,
                roe_3y_avg     REAL,
                market_cap     REAL,
                passed         INTEGER NOT NULL,
                score          REAL,
                reason         TEXT,
                UNIQUE(run_date, pool, symbol)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_screening_run_date ON cigar_butt_screening(run_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_screening_symbol   ON cigar_butt_screening(symbol)")
        conn.commit()
    finally:
        conn.close()


# ============================================================
# 数据拉取（带简单重试）
# ============================================================

def _retry(fn, tries: int = _RETRY_TIMES, sleep_s: float = 1.0):
    last_exc = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if i < tries - 1:
                time.sleep(sleep_s * (i + 1))
    raise last_exc if last_exc else RuntimeError("retry exhausted")


def get_pool(pool: str = "sse_dividend") -> pd.DataFrame:
    """获取候选池成分股（代码+名称）"""
    import akshare as ak
    cfg = POOLS[pool]
    df = _retry(lambda: ak.index_stock_cons_csindex(symbol=cfg["index_code"]))
    return df[["成分券代码", "成分券名称"]].rename(
        columns={"成分券代码": "symbol", "成分券名称": "name"}
    )


def fetch_value(symbol: str) -> Optional[dict]:
    """取最新一行 PE/PB/市值"""
    import akshare as ak
    try:
        df = _retry(lambda: ak.stock_value_em(symbol=symbol))
        if df is None or df.empty:
            return None
        row = df.iloc[-1]
        pe = row.get("PE(TTM)")
        pb = row.get("市净率")
        mc = row.get("总市值")
        return {
            "pe": float(pe) if pd.notna(pe) else None,
            "pb": float(pb) if pd.notna(pb) else None,
            "market_cap": float(mc) / 1e8 if pd.notna(mc) else None,  # 转亿元
            "date": row.get("数据日期"),
        }
    except Exception as e:
        logger.warning("[cigar_butt] fetch_value %s fail: %s", symbol, e)
        return None


def fetch_roe_3y_avg(symbol: str) -> Optional[float]:
    """取近 3 年年报 ROE 均值（净资产收益率(%)）"""
    import akshare as ak
    current_year = datetime.now().year
    start_year = str(current_year - 3)
    try:
        df = _retry(lambda: ak.stock_financial_analysis_indicator(symbol=symbol, start_year=start_year))
        if df is None or df.empty:
            return None
        # 只取年报（12-31）
        df["日期"] = pd.to_datetime(df["日期"])
        annual = df[df["日期"].dt.strftime("%m-%d") == "12-31"]
        if annual.empty:
            return None
        roes = annual["净资产收益率(%)"].dropna().tail(3)
        if len(roes) < 1:
            return None
        return float(roes.mean())
    except Exception as e:
        logger.warning("[cigar_butt] fetch_roe %s fail: %s", symbol, e)
        return None


def fetch_dividend_info(symbol: str, all_div: Optional[pd.DataFrame] = None) -> dict:
    """取分红次数 + 累计股息"""
    import akshare as ak
    try:
        if all_div is None:
            all_div = _retry(lambda: ak.stock_history_dividend())
        row = all_div[all_div["代码"] == symbol]
        if row.empty:
            return {"dividend_count": 0, "annual_dividend": None}
        r = row.iloc[0]
        return {
            "dividend_count": int(r.get("分红次数") or 0),
            "annual_dividend": float(r.get("年均股息") or 0),  # 单位：元/10股
        }
    except Exception as e:
        logger.warning("[cigar_butt] fetch_dividend %s fail: %s", symbol, e)
        return {"dividend_count": 0, "annual_dividend": None}


# ============================================================
# 筛选核心
# ============================================================

def _norm(x: float, a: float, b: float) -> float:
    """把 x 归一化到 [0, 100]"""
    if x is None:
        return 0.0
    v = (x - a) / (b - a)
    return max(0.0, min(1.0, v)) * 100


def _compute_score(rec: dict) -> float:
    """加权评分"""
    pb = rec.get("pb") or 999
    pe = rec.get("pe") or 999
    roe = rec.get("roe_3y_avg") or 0
    div_count = rec.get("dividend_count") or 0
    mc = rec.get("market_cap") or 0

    score = 0
    score += 0.30 * _norm(div_count, 5, 20)          # 分红习惯
    # PB 反向：PB 越低得分越高；区间 [0.3, 0.7] 对齐硬门槛 _MAX_PB=0.7
    pb_for_score = pb if isinstance(pb, (int, float)) and pb > 0 else 0.7
    score += 0.25 * _norm(0.7 - min(pb_for_score, 0.7), 0.0, 0.4)  # PB 反向
    score += 0.20 * _norm(roe, 0, 20)                # ROE
    score += 0.15 * _norm(1 / max(pe, 1), 0.1, 0.3)  # PE 反向
    score += 0.10 * _norm(mc, 100, 2000)             # 市值稳定性
    return round(score, 1)


def _check_hard_gate(rec: dict) -> tuple[bool, list[str]]:
    """硬门槛检查；返回 (passed, failure_reasons)"""
    reasons = []
    pb = rec.get("pb")
    pe = rec.get("pe")
    div_count = rec.get("dividend_count") or 0
    roe = rec.get("roe_3y_avg")

    if pb is None or pb >= _MAX_PB:
        reasons.append(f"PB={pb}≥{_MAX_PB}")
    if pe is None or pe <= 0 or pe >= _MAX_PE:
        reasons.append(f"PE={pe} 不在 (0, {_MAX_PE})")
    if div_count < _MIN_DIVIDEND_COUNT:
        reasons.append(f"分红次数={div_count}<{_MIN_DIVIDEND_COUNT}")
    if roe is None or roe <= _MIN_ROE_3Y_AVG:
        reasons.append(f"3年ROE={roe}≤{_MIN_ROE_3Y_AVG}")

    return len(reasons) == 0, reasons


# ============================================================
# 主入口
# ============================================================

def screen(pool: str = "sse_dividend", top_n: Optional[int] = None) -> list[dict]:
    """完整跑一次筛选 → 落库 → 返回结果列表（按 score 降序，通过在前）"""
    _init_table()
    import akshare as ak

    logger.info("[cigar_butt] 开始筛选 pool=%s", pool)
    pool_df = get_pool(pool)
    logger.info("[cigar_butt] 候选池 %d 只", len(pool_df))

    # 一次性拉全部分红数据（快）——失败直接 raise，避免“空 DF → 全城淘汰”
    all_div = _retry(lambda: ak.stock_history_dividend())
    if all_div is None or all_div.empty:
        raise RuntimeError("stock_history_dividend 返回空，无法判定分红门槛")

    results = []
    now_utc = datetime.utcnow()
    run_date = datetime.now().date()

    for i, r in enumerate(pool_df.itertuples(), 1):
        symbol, name = r.symbol, r.name
        logger.info("[cigar_butt] [%d/%d] %s %s", i, len(pool_df), symbol, name)

        val = fetch_value(symbol) or {}
        roe = fetch_roe_3y_avg(symbol)
        div = fetch_dividend_info(symbol, all_div=all_div)

        rec = {
            "symbol": symbol,
            "name": name,
            "pb": val.get("pb"),
            "pe": val.get("pe"),
            "market_cap": val.get("market_cap"),
            "roe_3y_avg": roe,
            "dividend_count": div["dividend_count"],
            "annual_dividend": div["annual_dividend"],
        }
        passed, reasons = _check_hard_gate(rec)
        rec["passed"] = passed
        rec["reason"] = None if passed else "; ".join(reasons)
        rec["score"] = _compute_score(rec) if passed else None
        results.append(rec)

        time.sleep(_SLEEP_BETWEEN_STOCKS)

    # 落库
    _save_all(results, pool, now_utc, run_date)

    # 排序：通过在前，按 score 降序；未通过按 PB 升序
    results.sort(key=lambda x: (not x["passed"], -(x["score"] or 0), x["pb"] or 999))

    if top_n:
        return results[:top_n]
    return results


def _save_all(records: list[dict], pool: str, run_ts: datetime, run_date: date) -> int:
    if not records:
        return 0
    rows = [
        {
            "run_ts": run_ts,
            "run_date": run_date,
            "pool": pool,
            "symbol": r["symbol"],
            "name": r["name"],
            "pb": r["pb"],
            "pe": r["pe"],
            "dividend_count": r["dividend_count"],
            "annual_dividend": r["annual_dividend"],
            "roe_3y_avg": r["roe_3y_avg"],
            "market_cap": r["market_cap"],
            "passed": 1 if r["passed"] else 0,
            "score": r["score"],
            "reason": r["reason"],
        }
        for r in records
    ]
    conn = sqlite3.connect(_DB_PATH)
    try:
        cur = conn.executemany("""
            INSERT OR REPLACE INTO cigar_butt_screening
              (run_ts, run_date, pool, symbol, name, pb, pe, dividend_count,
               annual_dividend, roe_3y_avg, market_cap, passed, score, reason)
            VALUES
              (:run_ts, :run_date, :pool, :symbol, :name, :pb, :pe, :dividend_count,
               :annual_dividend, :roe_3y_avg, :market_cap, :passed, :score, :reason)
        """, rows)
        conn.commit()
        return cur.rowcount or 0
    finally:
        conn.close()


# ============================================================
# 展示层
# ============================================================

def format_report(results: list[dict], pool: str = "sse_dividend") -> str:
    """周度报告格式"""
    passed = [r for r in results if r["passed"]]
    total = len(results)

    lines = [f"【🚬 烟蒂股筛选周报】"]
    lines.append(f"候选池：{POOLS[pool]['name']}（{total} 只）")
    lines.append(f"通过硬门槛：{len(passed)} 只（PB<{_MAX_PB} + PE<{_MAX_PE} + 分红≥{_MIN_DIVIDEND_COUNT}次 + 3年ROE>0）")
    lines.append("")

    if not passed:
        lines.append("⚠️ 本轮无股票通过硬门槛")
        # 展示前 5 只"最接近通过"的（PB 最低）
        near = sorted(results, key=lambda x: x["pb"] or 999)[:5]
        lines.append("")
        lines.append("最接近通过（按 PB 升序 Top5）：")
        for r in near:
            pb_s = f"{r['pb']:.2f}" if r['pb'] is not None else "-"
            pe_s = f"{r['pe']:.2f}" if r['pe'] is not None else "-"
            roe_s = f"{r['roe_3y_avg']:.2f}%" if r['roe_3y_avg'] is not None else "-"
            lines.append(
                f"  · {r['symbol']} {r['name']:<8} "
                f"PB={pb_s} PE={pe_s} 分红={r['dividend_count']}次 "
                f"ROE均={roe_s}  "
                f"→ 缺: {r['reason']}"
            )
        return "\n".join(lines)

    lines.append("─" * 66)
    lines.append(f"{'排名':<4}{'代码':<9}{'名称':<10}{'PB':>6}{'PE':>7}{'分红次数':>8}{'3Y ROE':>9}{'评分':>6}")
    for i, r in enumerate(passed, 1):
        name = r["name"][:6]
        pb = f"{r['pb']:.2f}" if r['pb'] is not None else "-"
        pe = f"{r['pe']:.2f}" if r['pe'] is not None else "-"
        dc = f"{r['dividend_count']}"
        roe = f"{r['roe_3y_avg']:.1f}%" if r['roe_3y_avg'] is not None else "-"
        sc = f"{r['score']:.1f}"
        lines.append(f"{i:<4}{r['symbol']:<9}{name:<10}{pb:>6}{pe:>7}{dc:>8}{roe:>9}{sc:>6}")

    # 极端提示（区分银行股 vs 其它行业）
    extreme_banks = [r for r in passed if r["pb"] is not None and r["pb"] < _EXTREME_LOW_PB and r["symbol"] in _BANK_SYMBOLS]
    extreme_others = [r for r in passed if r["pb"] is not None and r["pb"] < _EXTREME_LOW_PB and r["symbol"] not in _BANK_SYMBOLS]

    if extreme_others:
        lines.append("")
        lines.append(f"⚠️ 极端破净（PB<{_EXTREME_LOW_PB}）非银行股警示——需人工核实退市/暂停风险：")
        for r in extreme_others:
            lines.append(f"  · {r['symbol']} {r['name']} PB={r['pb']:.2f}")

    if extreme_banks:
        lines.append("")
        lines.append(f"ℹ️ 银行股深度破净（PB<{_EXTREME_LOW_PB}）——行业常态，属估值机会：")
        for r in extreme_banks:
            lines.append(f"  · {r['symbol']} {r['name']} PB={r['pb']:.2f}")

    return "\n".join(lines)


__all__ = ["screen", "format_report", "get_pool", "POOLS"]
