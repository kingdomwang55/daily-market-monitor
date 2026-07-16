"""
ETF 折溢价监控模块（重点跟踪 QDII/跨境 ETF）

数据源：
- 东财 fund_etf_spot_em（akshare）
  返回：最新价、IOPV 实时估值、基金折价率（东财已经算好）
  注意：东财"基金折价率" = (IOPV - 最新价) / IOPV × 100%
        负值 = 溢价（最新价 > IOPV，买贵了），正值 = 折价（最新价 < IOPV，便宜）
        为了直观，我们统一转换为「溢价率」= (最新价 / IOPV - 1) × 100%
        正值 = 溢价（拒追高），负值 = 折价（值得买）

策略：
- 溢价率 > +3%  → 拒追高（🔴 高危）
- 溢价率 > +1%  → 谨慎（🟡 观察）
- 溢价率 < -1%  → 买入等回归（🟢 机会）

罕见信号（|premium| > 5%）→ 交叉核实（同标的多只 ETF 比对）
"""

import logging
import sqlite3
from datetime import datetime, date, timedelta
from typing import Optional

from .db_path import ensure_sqlite_parent, sqlite_db_path

logger = logging.getLogger(__name__)

# 策略阈值
_HIGH_PREMIUM = 3.0    # >3% 拒追高
_WARN_PREMIUM = 1.0    # >1% 观察
_DISCOUNT_BUY = -1.0   # <-1% 值得买

# 罕见信号阈值
_RARE_THRESHOLD = 5.0  # |溢价| > 5% 触发交叉核实

# 分位数配置
_HIST_MIN_SAMPLES = 30
_HIST_WINDOW_DAYS = 250

# 快照存储
_DB_PATH = sqlite_db_path()


# ============================================================
# 核心跟踪 ETF 清单（QDII + 跨境 + 主要商品）
# 格式：(代码, 简称, 板块)
# ============================================================
CORE_ETFS = [
    # 美股 - QDII 高溢价高危区
    ("513100", "纳指ETF", "美股"),
    ("159941", "纳指ETF华夏", "美股"),  # 大规模
    ("513500", "标普500ETF博时", "美股"),
    ("513850", "美国50ETF易方达", "美股"),
    ("159509", "纳指科技ETF华夏", "美股"),
    # 港股 - 通道通畅，溢价小
    ("159920", "恒生ETF华夏", "港股"),
    ("513180", "恒生科技ETF华夏", "港股"),
    ("513330", "恒生互联网ETF华夏", "港股"),
    ("513090", "香港证券ETF易方达", "港股"),
    ("513060", "恒生医药ETF博时", "港股"),
    # 日/欧
    ("513520", "日经ETF华夏", "日股"),
    ("513000", "日经225ETF易方达", "日股"),
    ("513080", "法国ETF华安", "欧股"),
    ("513030", "德国ETF华安", "欧股"),
    # 大宗商品
    ("518880", "黄金ETF华安", "黄金"),
    ("159934", "黄金ETF易方达", "黄金"),
    ("162411", "华宝油气LOF", "原油"),
    ("161129", "南方原油LOF", "原油"),
    ("513350", "标普油气ETF富国", "原油"),
    ("159985", "豆粕ETF", "农产品"),
    ("159980", "有色ETF", "有色"),
]


def _init_snapshot_table():
    """初始化 ETF 溢价快照表"""
    ensure_sqlite_parent(_DB_PATH)
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS etf_premium_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT,
                sector TEXT,
                price REAL,
                iopv REAL,
                premium_pct REAL,
                UNIQUE(trade_date, code)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_etf_code_date ON etf_premium_snapshot(code, trade_date)")
        conn.commit()
    finally:
        conn.close()


def _save_snapshot(results: list[dict]) -> None:
    """将溢价数据落库（交易日去重）"""
    if not results:
        return
    _init_snapshot_table()
    now = datetime.utcnow().isoformat()
    today = date.today().isoformat()
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        rows = [
            (
                now, today, r["code"], r["name"], r["sector"],
                r["price"], r["iopv"], r["premium_pct"],
            )
            for r in results
        ]
        conn.executemany(
            """INSERT OR REPLACE INTO etf_premium_snapshot
               (ts, trade_date, code, name, sector, price, iopv, premium_pct)
               VALUES (?,?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
    except Exception as e:
        logger.warning("ETF 快照落库失败：%s", e)
    finally:
        conn.close()


def _get_hist_percentiles(code: str) -> Optional[dict]:
    """取个 ETF 历史分位数"""
    if not _DB_PATH.exists():
        return None
    cutoff = (date.today() - timedelta(days=_HIST_WINDOW_DAYS)).isoformat()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        rows = conn.execute(
            """SELECT premium_pct FROM etf_premium_snapshot
               WHERE code=? AND trade_date>=? AND premium_pct IS NOT NULL
               ORDER BY premium_pct""",
            (code, cutoff),
        ).fetchall()
        conn.close()
    except Exception as e:
        logger.warning("ETF 历史分位数查询失败：%s", e)
        return None

    values = [r[0] for r in rows]
    if len(values) < _HIST_MIN_SAMPLES:
        return None

    def _pct(pct: float) -> float:
        k = (len(values) - 1) * (pct / 100.0)
        f = int(k)
        c = min(f + 1, len(values) - 1)
        if f == c:
            return values[f]
        return values[f] + (values[c] - values[f]) * (k - f)

    return {
        "n": len(values),
        "p20": _pct(20),
        "p50": _pct(50),
        "p80": _pct(80),
        "min": values[0],
        "max": values[-1],
    }


def fetch_etf_premium() -> list[dict]:
    """
    获取核心 ETF 的实时折溢价数据

    Returns: [{
        "code": str,           # ETF 代码
        "name": str,           # 简称
        "sector": str,         # 板块
        "price": float,        # 最新价
        "iopv": float,         # IOPV 实时估值
        "premium_pct": float,  # 溢价率（%），正=溢价，负=折价
        "signal": str,         # "high_premium" / "warn_premium" / "buy_discount" / "normal"
        "hist": dict | None,   # 历史分位数
    }] 按 |溢价率| 降序
    """
    try:
        import akshare as ak
        df = ak.fund_etf_spot_em()
    except Exception as e:
        logger.warning("拉取 ETF 数据失败：%s", e)
        return []

    # 建立代码 → 行 的映射
    code_col = "代码" if "代码" in df.columns else "symbol"
    df_map = {str(row[code_col]).zfill(6): row for _, row in df.iterrows()}

    results = []
    for code, name, sector in CORE_ETFS:
        row = df_map.get(code)
        if row is None:
            continue
        try:
            price = float(row["最新价"])
            iopv = float(row["IOPV实时估值"])
            if price <= 0 or iopv <= 0:
                continue
            # 统一为「溢价率」：正值 = 溢价（贵）、负值 = 折价（便宜）
            premium_pct = (price / iopv - 1.0) * 100.0
        except (KeyError, ValueError, TypeError):
            continue

        # 判定信号等级
        if premium_pct >= _HIGH_PREMIUM:
            signal = "high_premium"
        elif premium_pct >= _WARN_PREMIUM:
            signal = "warn_premium"
        elif premium_pct <= _DISCOUNT_BUY:
            signal = "buy_discount"
        else:
            signal = "normal"

        results.append({
            "code": code,
            "name": name,
            "sector": sector,
            "price": price,
            "iopv": iopv,
            "premium_pct": premium_pct,
            "signal": signal,
        })

    # 落库
    try:
        _save_snapshot(results)
    except Exception as e:
        logger.warning("ETF 快照存储异常：%s", e)

    # 附上历史分位数
    for r in results:
        r["hist"] = _get_hist_percentiles(r["code"])

    # 按 |溢价率| 降序
    results.sort(key=lambda x: abs(x["premium_pct"]), reverse=True)
    return results


def _cross_check_sector_peers(target: dict, all_results: list[dict]) -> Optional[dict]:
    """罕见信号交叉核实：同板块其他 ETF 溢价率对比

    如果同板块多只 ETF 都出现类似溢价，说明是标的因素（额度限制/供需）
    如果只有这只 ETF 溢价，说明可能是数据异常或个别流动性问题
    """
    peers = [r for r in all_results
             if r["sector"] == target["sector"] and r["code"] != target["code"]]
    if not peers:
        return None
    peer_prem = [r["premium_pct"] for r in peers]
    avg = sum(peer_prem) / len(peer_prem)
    max_prem = max(peer_prem)
    min_prem = min(peer_prem)
    # 判断是否一致
    consistent = abs(target["premium_pct"] - avg) < 2.0  # 差异 < 2%
    return {
        "peer_count": len(peers),
        "peer_avg": avg,
        "peer_max": max_prem,
        "peer_min": min_prem,
        "consistent": consistent,
        "verdict": "标的性因素（额度/供需）" if consistent else "个别异常，建议人工复核",
    }


def get_signals(results: list[dict], verify_rare: bool = True) -> list[dict]:
    """提取交易信号

    优先级：
    1. 有历史分位（≥30 天）→ 用 P20/P80 判定极端
    2. 无历史 → 用固定阈值（3%/1%/-1%）
    3. |溢价| > 5% 触发交叉核实（同板块 peers 比对）
    """
    signals = []
    for r in results:
        premium_pct = r["premium_pct"]
        hist = r.get("hist")

        # 阈值选择
        if hist:
            th_high = hist["p80"]
            th_low = hist["p20"]
            basis = f"P20={hist['p20']:+.2f}% / P80={hist['p80']:+.2f}% · n={hist['n']}"
            is_high = premium_pct >= th_high and premium_pct >= _WARN_PREMIUM
            is_low = premium_pct <= th_low and premium_pct <= _DISCOUNT_BUY
        else:
            basis = "固定阈值（历史快照不足 30 天）"
            is_high = premium_pct >= _WARN_PREMIUM
            is_low = premium_pct <= _DISCOUNT_BUY

        if not (is_high or is_low):
            continue

        rare = abs(premium_pct) > _RARE_THRESHOLD
        cross_check = None
        if rare and verify_rare:
            cross_check = _cross_check_sector_peers(r, results)

        if is_high:
            level = "🔴" if premium_pct >= _HIGH_PREMIUM else "🟡"
            action = f"{level} 拒追高 · {r['name']} ({r['code']})"
            reason = f"溢价 {premium_pct:+.2f}%（IOPV {r['iopv']:.3f} · 现价 {r['price']:.3f}）"
            direction = "avoid_chase"
        else:  # is_low
            action = f"🟢 折价买入 · {r['name']} ({r['code']})"
            reason = f"折价 {premium_pct:+.2f}%（IOPV {r['iopv']:.3f} · 现价 {r['price']:.3f}）"
            direction = "buy_discount"

        signals.append({
            "code": r["code"],
            "name": r["name"],
            "sector": r["sector"],
            "premium_pct": premium_pct,
            "direction": direction,
            "action": action,
            "reason": reason,
            "basis": basis,
            "rare": rare,
            "cross_check": cross_check,
        })

    return signals


def format_summary(results: list[dict], top_n: int = 20) -> str:
    """格式化 ETF 溢价概览"""
    if not results:
        return "📊 ETF 折溢价：暂无数据"

    lines = [f"📊 **ETF 折溢价概览**（核心 {len(results)} 只 QDII/跨境/商品）"]
    lines.append("")
    lines.append("| 板块 | ETF | 现价 | IOPV | 溢价 | 状态 |")
    lines.append("|------|-----|-----|------|------|------|")

    for r in results[:top_n]:
        icon = {
            "high_premium": "🔴 拒追高",
            "warn_premium": "🟡 观察",
            "buy_discount": "🟢 折价",
            "normal": "⚪ 正常",
        }.get(r["signal"], "•")
        lines.append(
            f"| {r['sector']} | {r['name']} | "
            f"{r['price']:.3f} | {r['iopv']:.3f} | "
            f"{r['premium_pct']:+.2f}% | {icon} |"
        )

    return "\n".join(lines)


def format_signals(signals: list[dict]) -> str:
    """格式化交易信号"""
    if not signals:
        return "📡 ETF 折溢价：当前无极端信号"

    lines = ["📡 **ETF 折溢价信号**"]
    for s in signals:
        rare_mark = " ⚠️罕见" if s.get("rare") else ""
        lines.append(f"  {s['action']}{rare_mark}")
        lines.append(f"    • {s['reason']}")
        if s.get("basis"):
            lines.append(f"    • 依据：{s['basis']}")
        if s.get("rare") and s.get("cross_check"):
            cc = s["cross_check"]
            icon = "✅" if cc["consistent"] else "⚠️"
            lines.append(
                f"    • 同板块 {cc['peer_count']} 只 peers 均值 {cc['peer_avg']:+.2f}%，"
                f"{icon} {cc['verdict']}"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    results = fetch_etf_premium()
    print(f"成功获取 {len(results)}/{len(CORE_ETFS)} 只 ETF\n")
    print(format_summary(results))
    print()
    signals = get_signals(results)
    print(format_signals(signals))
