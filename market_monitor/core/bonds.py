"""债券收益率曲线与利差监控（Bond Yield Curve & Spreads）

P1-2：在美国 10Y 基础上扩展 2Y/5Y/30Y，计算关键利差。
Yahoo Finance 数据源：^IRX(13周) / ^FVX(5Y) / ^TNX(10Y) / ^TYX(30Y)

核心功能：
- fetch_bonds() → 拉取各期限收益率
- calc_spreads() → 计算关键利差（2Y10Y / 5Y30Y / 2Y10Y 倒挂检测）
- format_bonds() → 格式化文本（报告用）
- bonds_summary_for_ai() → 紧凑版（AI prompt 用）
- analyze_yield_curve() → 收益率曲线形态信号
"""
from typing import Dict, List, Optional
from . import data_source as ds


# Yahoo 债券符号
BOND_SYMBOLS = [
    ("^IRX", "美债13周", "短端"),
    ("^FVX", "美债5Y", "中短端"),
    ("^TNX", "美债10Y", "中长端"),
    ("^TYX", "美债30Y", "长端"),
]


def fetch_bonds() -> Dict[str, dict]:
    """拉取各期限美债收益率

    Returns:
        {name: {price, prev, pct, term}, ...}
        price = 收益率百分比，如 4.513 = 4.513%
    """
    result = {}
    for symbol, name, term in BOND_SYMBOLS:
        q = ds.yahoo_quote(symbol)
        if q:
            q["term"] = term
            q["symbol"] = symbol
            result[name] = q
    return result


def calc_spreads(bonds: Dict[str, dict]) -> Dict[str, float]:
    """计算关键利差（单位：基点 bp）

    Returns:
        {
            "2Y10Y": 利差(bp),  # 正=正常，负=倒挂
            "5Y30Y": 利差(bp),
            "13周10Y": 利差(bp),
            "inverted": bool,  # 2Y10Y 是否倒挂
        }
    """
    # Yahoo 没有 2Y，用 13周(T-bill) 近似短端
    # 实际有 ^FVX(5Y) 和 ^TNX(10Y) 和 ^TYX(30Y)
    tnx = bonds.get("美债10Y", {}).get("price")
    fvx = bonds.get("美债5Y", {}).get("price")
    tyx = bonds.get("美债30Y", {}).get("price")
    irx = bonds.get("美债13周", {}).get("price")

    spreads = {}
    if irx is not None and tnx is not None:
        spreads["13周-10Y"] = round((tnx - irx) * 100, 1)  # bp
    if fvx is not None and tnx is not None:
        spreads["5Y-10Y"] = round((tnx - fvx) * 100, 1)
    if fvx is not None and tyx is not None:
        spreads["5Y-30Y"] = round((tyx - fvx) * 100, 1)
    if irx is not None and tnx is not None:
        spreads["inverted"] = tnx < irx  # 10Y < 13周 = 严重倒挂
    else:
        spreads["inverted"] = False
    return spreads


def format_bonds(bonds: Dict[str, dict], spreads: Dict) -> str:
    """格式化为报告文本"""
    if not bonds:
        return ""
    lines = ["【美债收益率曲线】"]
    for name, q in bonds.items():
        price = q.get("price", 0)
        pct = q.get("pct", 0)
        lines.append(f"  {name:8s}: {price:>6.3f}% ({pct:+.2f}%)")

    if spreads:
        lines.append("")
        inv = spreads.get("inverted")
        for key in ["13周-10Y", "5Y-10Y", "5Y-30Y"]:
            val = spreads.get(key)
            if val is not None:
                tag = ""
                if key == "13周-10Y" and inv:
                    tag = " ⚠️倒挂"
                elif val < 0:
                    tag = " ⚠️倒挂"
                lines.append(f"  利差 {key}: {val:+.1f} bp{tag}")
    return "\n".join(lines)


def bonds_summary_for_ai(bonds: Dict[str, dict], spreads: Dict) -> str:
    """给 AI 看的紧凑版"""
    if not bonds:
        return "债券：无数据"
    parts = ["美债收益率曲线："]
    for name, q in bonds.items():
        price = q.get("price", 0)
        pct = q.get("pct", 0)
        parts.append(f"- {name}: {price:.3f}% (日变 {pct:+.2f}%)")
    if spreads:
        inv = spreads.get("inverted")
        for key in ["13周-10Y", "5Y-10Y", "5Y-30Y"]:
            val = spreads.get(key)
            if val is not None:
                parts.append(f"- 利差 {key}: {val:+.1f} bp{' (倒挂!)' if val < 0 else ''}")
        if inv:
            parts.append("⚠️ 收益率曲线倒挂，经济衰退风险信号")
    return "\n".join(parts)


def analyze_yield_curve(bonds: Dict[str, dict], spreads: Dict) -> List[Dict]:
    """收益率曲线形态信号检测

    Returns:
        [{name, narrative, severity, affected}, ...]
    """
    signals = []
    inverted = spreads.get("inverted", False)

    if inverted:
        signals.append({
            "name": "收益率曲线倒挂",
            "narrative": (
                "短端利率高于长端 → 收益率曲线倒挂\n"
                "  ↓ 历史上倒挂后 6-18 个月可能进入衰退\n"
                "  ↓ 传导：避险资产（黄金/美债）受益，股票估值承压"
            ),
            "severity": "high",
            "affected": ["纳斯达克", "上证指数", "沪金主力"],
        })

    # 10Y 收益率快速变动
    tnx = bonds.get("美债10Y", {})
    tnx_pct = tnx.get("pct", 0)
    if tnx_pct >= 2.0:
        signals.append({
            "name": "美债10Y收益率急升",
            "narrative": (
                f"美债10Y 收益率单日上升 {tnx_pct:+.2f}% → 利率敏感型资产承压\n"
                "  ↓ 传导：成长股估值压缩，房地产股承压，新兴市场资金外流"
            ),
            "severity": "high",
            "affected": ["纳斯达克", "创业板指", "上证指数"],
        })
    elif tnx_pct <= -2.0:
        signals.append({
            "name": "美债10Y收益率回落",
            "narrative": (
                f"美债10Y 收益率单日下降 {tnx_pct:+.2f}% → 降息预期升温\n"
                "  ↓ 传导：成长股估值扩张受益，黄金受益"
            ),
            "severity": "medium",
            "affected": ["纳斯达克", "创业板指"],
        })

    # 5Y-30Y 利差过窄
    spread_5_30 = spreads.get("5Y-30Y")
    if spread_5_30 is not None and spread_5_30 < 10:
        signals.append({
            "name": "5Y-30Y 利差极度收窄",
            "narrative": (
                f"5Y-30Y 利差仅 {spread_5_30:.1f} bp → 市场对长期增长预期悲观\n"
                "  ↓ 传导：防御性板块相对占优，周期股承压"
            ),
            "severity": "medium",
            "affected": ["上证指数"],
        })

    return signals
