"""
AH 溢价套利监控模块（精简版：核心 20 只蓝筹）

数据源：
- A 股实时价：新浪 hq.sinajs.cn
- 港股实时价：新浪 hq.sinajs.cn
- 汇率：新浪 USDCNH → 换算为 HKD/CNY
- 罕见信号交叉验证：akshare stock_zh_ah_spot（腾讯财经）

计算逻辑：
  溢价率 = (A股价格 / (H股价格 × HKD_CNY) - 1) × 100%
  正值 = A 股比 H 股贵（A 股溢价，H 股折价）→ 关注 H 股做多
  负值 = H 股比 A 股贵（罕见）→ 关注 A 股做多

策略：
- 有历史快照（≥30 个交易日） → 用 P20/P80 分位数判定极端
- 无历史快照            → 用固定阈值（>40% H 股低估、<0% A 股低估）
- 内地不能做空 → 只做多低估方

罕见信号（负溢价）→ 触发第二数据源交叉核实
"""

import logging
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 港币兑人民币默认值（当 USDCNH 拉取失败时用）
_DEFAULT_HKD_CNY = 0.93

# 策略阈值（无历史快照时的兜底）
_H_UNDERVALUE_THRESHOLD = 0.40   # A 股溢价 > 40% → H 股低估
_A_UNDERVALUE_THRESHOLD = 0.00   # A 股折价（罕见）→ A 股低估

# 分位数计算配置
_HIST_MIN_SAMPLES = 30           # 少于 30 个样本用固定阈值
_HIST_WINDOW_DAYS = 250          # 分位数计算窗口（约 1 年）
_PERCENTILE_LOW = 20             # A 股低估分位（罕见）
_PERCENTILE_HIGH = 80            # H 股低估分位

# 快照存储路径（独立 SQLite 表，不污染主 models.py）
_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "market.db"


def _init_snapshot_table():
    """确保快照表存在（幂等）"""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ah_premium_snapshot (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                a_code TEXT NOT NULL,
                hk_code TEXT NOT NULL,
                name TEXT,
                sector TEXT,
                a_price REAL,
                h_price REAL,
                hkd_cny REAL,
                premium REAL,
                UNIQUE(trade_date, a_code)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ah_a_code_date ON ah_premium_snapshot(a_code, trade_date)")
        conn.commit()
    finally:
        conn.close()


# ============================================================
# 核心 20 只 AH 股映射（手工校验，2026-07-10）
# 格式：(A股代码, 港股代码, 中文名, 板块)
# ============================================================
CORE_AH_PAIRS = [
    # 银行 6 只
    ("601398", "01398", "工商银行", "银行"),
    ("601939", "00939", "建设银行", "银行"),
    ("601288", "01288", "农业银行", "银行"),
    ("601988", "03988", "中国银行", "银行"),
    ("601328", "03328", "交通银行", "银行"),
    ("600036", "03968", "招商银行", "银行"),
    # 保险 3 只
    ("601318", "02318", "中国平安", "保险"),
    ("601628", "02628", "中国人寿", "保险"),
    ("601601", "02601", "中国太保", "保险"),
    # 券商 2 只
    ("600030", "06030", "中信证券", "券商"),
    ("601688", "06886", "华泰证券", "券商"),
    # 能源/资源 4 只
    ("601857", "00857", "中国石油", "能源"),
    ("600028", "00386", "中国石化", "能源"),
    ("601088", "01088", "中国神华", "能源"),
    ("601899", "02899", "紫金矿业", "有色"),
    # 通信 3 只
    ("600941", "00941", "中国移动", "通信"),
    ("601728", "00728", "中国电信", "通信"),
    ("600050", "00762", "中国联通", "通信"),
    # 制造 2 只
    ("002594", "01211", "比亚迪",   "汽车"),
    ("601766", "01766", "中国中车", "高端制造"),
]


def _save_snapshot(results: list[dict], hkd_cny: float) -> None:
    """将当前溢价快照写入 SQLite（每个交易日去重）"""
    if not results:
        return
    _init_snapshot_table()
    now = datetime.utcnow()
    today = date.today().isoformat()
    conn = sqlite3.connect(str(_DB_PATH))
    try:
        rows = [
            (
                now.isoformat(),
                today,
                r["a_code"],
                r["hk_code"],
                r["name"],
                r["sector"],
                r["a_price"],
                r["h_price"],
                hkd_cny,
                r["premium"],
            )
            for r in results
        ]
        conn.executemany(
            """INSERT OR REPLACE INTO ah_premium_snapshot
               (ts, trade_date, a_code, hk_code, name, sector,
                a_price, h_price, hkd_cny, premium)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
    except Exception as e:
        logger.warning("AH 快照落库失败：%s", e)
    finally:
        conn.close()


def _get_hist_percentiles(a_code: str) -> Optional[dict]:
    """取个股历史分位数（P20/P50/P80），不够 30 个样本返回 None"""
    if not _DB_PATH.exists():
        return None
    cutoff = (date.today() - timedelta(days=_HIST_WINDOW_DAYS)).isoformat()
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        rows = conn.execute(
            """SELECT premium FROM ah_premium_snapshot
               WHERE a_code=? AND trade_date>=? AND premium IS NOT NULL
               ORDER BY premium""",
            (a_code, cutoff),
        ).fetchall()
        conn.close()
    except Exception as e:
        logger.warning("历史分位数查询失败：%s", e)
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


def _cross_check_akshare(a_code: str, hk_code: str) -> Optional[dict]:
    """罕见信号交叉验证：用 akshare 拿腾讯 AH 行情重新算一次"""
    try:
        import akshare as ak
        df = ak.stock_zh_ah_spot()
        # 腾讯 ‘代码’ 列存的是港股代码。可能包含前导零（如 01398）也可能不包含（5）
        hk_int = str(int(hk_code))                       # "01398" -> "1398"
        hk_full = hk_code.lstrip("0") or hk_code          # 处理全零边界
        for col in ["代码", "symbol", "code"]:
            if col in df.columns:
                mask = df[col].astype(str).isin([hk_code, hk_int, hk_full, f"hk{hk_int}"])
                sub = df[mask]
                if not sub.empty:
                    row = sub.iloc[0].to_dict()
                    return {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in row.items()}
        return None
    except Exception as e:
        logger.warning("akshare 交叉验证失败：%s", e)
        return None


def _get_hkd_to_cny() -> float:
    """获取港币兑人民币汇率（从新浪实时 USDCNH 换算）"""
    try:
        from .data_source import http_get
        raw = http_get("https://hq.sinajs.cn/list=fx_susdcnh", encoding="gbk")
        # 格式：var hq_str_fx_susdcnh="Wed May 15 22:35:03 2024,7.2345,7.2350,..."
        parts = raw.split('"')[1].split(",")
        if len(parts) >= 2:
            usdcnh = float(parts[1])
            # HKD 挂钩 USD，HKD/CNY ≈ USDCNH / 7.85（港币联系汇率制）
            return usdcnh / 7.85
    except Exception as e:
        logger.warning("获取汇率失败，使用默认 0.93: %s", e)
    return _DEFAULT_HKD_CNY


def _fetch_prices(a_codes: list[str], hk_codes: list[str]) -> dict:
    """
    批量拉取 A 股 + 港股实时价格

    Returns: {
        "a": {code: {"price": float, "change": float}, ...},
        "h": {code: {"price": float, "change": float}, ...}
    }
    """
    from .data_source import http_get

    # A 股：sh600036,sh601398,sz002594,...
    a_symbols = []
    for c in a_codes:
        if c.startswith("6"):
            a_symbols.append(f"sh{c}")
        elif c.startswith(("0", "3")):
            a_symbols.append(f"sz{c}")

    # 港股：rt_hk01398 需要 5 位数字（自动补零已在代码里）
    hk_symbols = [f"rt_hk{c}" for c in hk_codes]

    all_symbols = a_symbols + hk_symbols
    url = "https://hq.sinajs.cn/list=" + ",".join(all_symbols)
    raw = http_get(url, encoding="gbk")

    result = {"a": {}, "h": {}}

    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line or "=" not in line:
            continue
        # 提取 symbol 和 payload
        try:
            head, payload = line.split("=", 1)
            symbol = head.replace("var hq_str_", "").strip()
            payload = payload.strip().strip(";").strip('"')
        except Exception:
            continue

        parts = payload.split(",")

        # A 股：sh600036 or sz002594
        if symbol.startswith("sh") or symbol.startswith("sz"):
            code = symbol[2:]
            if len(parts) < 4:
                continue
            try:
                # 新浪 A 股：[名称, 今开, 昨收, 现价, 最高, ...]
                prev_close = float(parts[2])
                cur_price = float(parts[3])
                if prev_close > 0 and cur_price > 0:
                    change_pct = (cur_price / prev_close - 1) * 100
                    result["a"][code] = {
                        "price": cur_price,
                        "change": change_pct,
                        "name": parts[0],
                    }
            except (ValueError, IndexError):
                continue

        # 港股：rt_hk01398
        elif symbol.startswith("rt_hk"):
            code = symbol[5:]
            if len(parts) < 10:
                continue
            try:
                # 新浪港股 rt_hk：[英文名, 中文名, 今开, 昨收, 最高, 最低, 现价, ...]
                prev_close = float(parts[3])
                cur_price = float(parts[6])
                if prev_close > 0 and cur_price > 0:
                    change_pct = (cur_price / prev_close - 1) * 100
                    result["h"][code] = {
                        "price": cur_price,
                        "change": change_pct,
                        "name": parts[1],
                    }
            except (ValueError, IndexError):
                continue

    return result


def fetch_ah_premium() -> list[dict]:
    """
    获取核心 20 只 AH 股的实时溢价数据

    Returns: [{
        "name": str,           # 公司中文名
        "sector": str,         # 板块
        "a_code": str,         # A 股代码
        "hk_code": str,        # 港股代码
        "a_price": float,      # A 股价（人民币）
        "h_price": float,      # H 股价（港币）
        "h_price_cny": float,  # H 股价换算成人民币
        "premium": float,      # 溢价率（小数，0.35 = 35%）
        "premium_pct": float,  # 溢价率（百分比，35.0）
        "direction": str,      # H 股低估 / A 股低估 / 正常
        "a_change": float,     # A 股涨跌幅（%）
        "h_change": float,     # H 股涨跌幅（%）
    }, ...] 按溢价率绝对值降序
    """
    hkd_cny = _get_hkd_to_cny()
    a_codes = [p[0] for p in CORE_AH_PAIRS]
    hk_codes = [p[1] for p in CORE_AH_PAIRS]

    prices = _fetch_prices(a_codes, hk_codes)

    results = []
    for a_code, hk_code, name, sector in CORE_AH_PAIRS:
        a_info = prices["a"].get(a_code)
        h_info = prices["h"].get(hk_code)

        if not a_info or not h_info:
            logger.warning("缺数据：%s A=%s H=%s", name, bool(a_info), bool(h_info))
            continue

        a_price = a_info["price"]
        h_price = h_info["price"]

        if a_price <= 0 or h_price <= 0:
            continue

        # 溢价率 = A 股价 / (H 股价 × 汇率) - 1
        # 正值 = A 股溢价（A 比 H 贵）
        h_in_cny = h_price * hkd_cny
        premium = (a_price / h_in_cny) - 1.0

        if premium > _H_UNDERVALUE_THRESHOLD:
            direction = "H 股低估"
        elif premium < _A_UNDERVALUE_THRESHOLD:
            direction = "A 股低估"
        else:
            direction = "正常"

        results.append({
            "name": name,
            "sector": sector,
            "a_code": a_code,
            "hk_code": hk_code,
            "a_price": a_price,
            "h_price": h_price,
            "h_price_cny": h_in_cny,
            "premium": premium,
            "premium_pct": premium * 100,
            "direction": direction,
            "a_change": a_info["change"],
            "h_change": h_info["change"],
        })

    # 按溢价率绝对值降序
    results.sort(key=lambda x: abs(x["premium"]), reverse=True)

    # 落库（仅交易日一次，UNIQUE 约束自动去重）
    try:
        _save_snapshot(results, hkd_cny)
    except Exception as e:
        logger.warning("AH 快照存储异常：%s", e)

    # 附上历史分位数
    for r in results:
        r["hist"] = _get_hist_percentiles(r["a_code"])

    return results


def get_signals(results: list[dict], verify_rare: bool = True) -> list[dict]:
    """从 AH 溢价数据中提取交易信号（内地只做多低估方）

    - 有历史：用 P20 (A 股低估) / P80 (H 股低估) 作为阈值
    - 无历史：用固定阈值（基线）
    - verify_rare=True 时，罕见信号（A 股低估）自动用 akshare 交叉核实
    """
    signals = []
    for r in results:
        hist = r.get("hist")
        premium = r["premium"]
        premium_pct = r["premium_pct"]

        # 阈值选择：历史分位优先，否则用固定阈值
        if hist:
            th_high = hist["p80"]
            th_low = hist["p20"]
            basis = f"P20={hist['p20']*100:.1f}% / P80={hist['p80']*100:.1f}% · n={hist['n']}"
        else:
            th_high = _H_UNDERVALUE_THRESHOLD
            th_low = _A_UNDERVALUE_THRESHOLD
            basis = "固定阈值（历史快照不足 30 天）"

        if premium >= th_high:
            signals.append({
                "name": r["name"],
                "sector": r["sector"],
                "a_code": r["a_code"],
                "hk_code": r["hk_code"],
                "premium_pct": premium_pct,
                "direction": "long_hk",
                "basis": basis,
                "action": f"关注 {r['name']}H 股 ({r['hk_code']})",
                "reason": f"A 股溢价 {premium_pct:+.1f}%，突破高位阈值",
                "rare": False,
            })
        elif premium <= th_low:
            # 罕见信号：A 股折价（负溢价或跌至历史低位）
            verify = None
            if verify_rare:
                verify = _cross_check_akshare(r["a_code"], r["hk_code"])
            signals.append({
                "name": r["name"],
                "sector": r["sector"],
                "a_code": r["a_code"],
                "hk_code": r["hk_code"],
                "premium_pct": premium_pct,
                "direction": "long_a",
                "basis": basis,
                "action": f"关注 {r['name']}A 股 ({r['a_code']})",
                "reason": f"A 股折价 {abs(premium_pct):.1f}%，低于历史 P20",
                "rare": True,
                "cross_check": verify,
            })
    return signals


def _get_signals_LEGACY(results: list[dict]) -> list[dict]:
    """[DEPRECATED] 旧固定阈值实现，留作回退"""
    signals = []
    for r in results:
        if r["direction"] == "H 股低估":
            signals.append({
                "name": r["name"],
                "sector": r["sector"],
                "a_code": r["a_code"],
                "hk_code": r["hk_code"],
                "premium_pct": r["premium_pct"],
                "direction": "long_hk",
                "action": f"关注 {r['name']}H 股 ({r['hk_code']})",
                "reason": f"A 股溢价 {r['premium_pct']:.1f}%，H 股相对便宜",
            })
        elif r["direction"] == "A 股低估":
            signals.append({
                "name": r["name"],
                "sector": r["sector"],
                "a_code": r["a_code"],
                "hk_code": r["hk_code"],
                "premium_pct": r["premium_pct"],
                "direction": "long_a",
                "action": f"关注 {r['name']}A 股 ({r['a_code']})",
                "reason": f"A 股折价 {abs(r['premium_pct']):.1f}%，A 股罕见便宜",
            })
    return signals


def format_summary(results: list[dict], top_n: int = 20) -> str:
    """格式化 AH 溢价概览（Markdown）"""
    if not results:
        return "📊 AH 溢价：暂无数据"

    lines = [f"📊 **AH 溢价概览**（核心 {len(results)} 只蓝筹，按溢价降序）"]
    lines.append("")
    lines.append("| 名称 | 板块 | A股 | H股 | 溢价 | 历史分位 |")
    lines.append("|------|------|-----|-----|-------|---------|")

    for r in results[:top_n]:
        hist = r.get("hist")
        if hist:
            # 换算当前分位（将 premium 与历史列表比对）
            pct_position = _calc_current_percentile(r["premium"], hist)
            hist_str = f"P{pct_position:.0f} · n={hist['n']}"
        else:
            hist_str = "历史不足"
        lines.append(
            f"| {r['name']} | {r['sector']} | "
            f"{r['a_price']:.2f} | {r['h_price']:.2f} | "
            f"{r['premium_pct']:+.1f}% | {hist_str} |"
        )

    return "\n".join(lines)


def _calc_current_percentile(premium: float, hist: dict) -> float:
    """根据历史分位定位当前溢价位置（粗估，0-100）"""
    if not hist:
        return 50.0
    if premium <= hist["p20"]:
        return 20.0 * (premium - hist["min"]) / max(hist["p20"] - hist["min"], 1e-9)
    if premium <= hist["p50"]:
        return 20.0 + 30.0 * (premium - hist["p20"]) / max(hist["p50"] - hist["p20"], 1e-9)
    if premium <= hist["p80"]:
        return 50.0 + 30.0 * (premium - hist["p50"]) / max(hist["p80"] - hist["p50"], 1e-9)
    return 80.0 + 20.0 * (premium - hist["p80"]) / max(hist["max"] - hist["p80"], 1e-9)


def format_signals(signals: list[dict]) -> str:
    """格式化交易信号（含分位依据、罕见信号交叉验证）"""
    if not signals:
        return "📡 AH 溢价：当前无极端信号"

    lines = ["📡 **AH 溢价信号**"]
    for s in signals:
        icon = "🇭🇰" if s["direction"] == "long_hk" else "🇨🇳"
        rare_mark = " ⚠️罕见" if s.get("rare") else ""
        lines.append(f"  {icon} {s['action']}{rare_mark}")
        lines.append(f"    • {s['reason']}")
        if s.get("basis"):
            lines.append(f"    • 依据：{s['basis']}")
        if s.get("rare") and s.get("cross_check") is not None:
            cc = s["cross_check"]
            if cc:
                lines.append(f"    • 交叉核实（腾讯/akshare）✅：{cc}")
            else:
                lines.append(f"    • 交叉核实（腾讯/akshare）❌ 未命中，建议人工复核")
    return "\n".join(lines)


if __name__ == "__main__":
    results = fetch_ah_premium()
    print(f"成功获取 {len(results)}/{len(CORE_AH_PAIRS)} 只 AH 股\n")
    print(format_summary(results))
    print()
    signals = get_signals(results)
    print(format_signals(signals))
