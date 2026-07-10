"""债券收益率曲线与利差分析（Bond Yield Curve & Spread）

监控美债关键期限收益率，计算利差，判断市场对利率路径的定价：
1. 3M/10Y 利差 —— Fed 官方关注的衰退指标（倒挂 = 强衰退信号）
2. 5Y/30Y 利差 —— 长端通胀预期 + 期限溢价

注：Yahoo 无 2 年期国债收益率符号，故不计算 2Y/10Y 利差

数据源：Yahoo Finance (^IRX=3M, ^FVX=5Y, ^TNX=10Y, ^TYX=30Y)
注意：Yahoo 返回的是收益率百分比（如 4.48 = 4.48%），不是价格

利差单位：基点 (bp)，1bp = 0.01%
"""
from typing import Dict, List, Optional

from . import data_source as ds


# ── 美债关键期限 ────────────────────────────────────────────
BOND_SYMBOLS = [
    ("^IRX", "美债3M", 13),   # 13-week T-bill
    ("^FVX", "美债5Y", 5),
    ("^TNX", "美债10Y", 10),
    ("^TYX", "美债30Y", 30),
]

# 关键利差对（用于计算 + 判断形态）
SPREAD_PAIRS = [
    {
        "name": "3M/10Y 利差",
        "short_key": "美债3M",
        "long_key": "美债10Y",
        "description": "Fed 官方关注的衰退指标：倒挂 = 强衰退信号",
        "critical_level": 0,
    },
    {
        "name": "5Y/30Y 利差",
        "short_key": "美债5Y",
        "long_key": "美债30Y",
        "description": "长端通胀预期 + 期限溢价：收窄 = 通胀预期回落",
        "critical_level": 0.5,
    },
]


def fetch_all_yields() -> Dict[str, Dict]:
    """拉取所有美债关键期限收益率"""
    result = {}
    for symbol, name, _years in BOND_SYMBOLS:
        try:
            q = ds.yahoo_quote(symbol)
            if q:
                result[name] = q
        except Exception as e:
            print(f"[bond_curve] {name} 拉取失败: {e}")
    return result


def calc_spreads(yields: Dict[str, Dict]) -> List[Dict]:
    """计算关键利差

    Returns:
        [
            {
                "name": "3M/10Y 利差",
                "short_yield": 4.38,
                "long_yield": 4.48,
                "spread_bp": 10,  # 基点
                "inverted": False,
                "description": "...",
                "severity": "normal" | "warning" | "critical",
            },
            ...
        ]
    """
    spreads = []
    for pair in SPREAD_PAIRS:
        short_data = yields.get(pair["short_key"])
        long_data = yields.get(pair["long_key"])
        if not short_data or not long_data:
            continue

        short_yield = short_data.get("price") or short_data.get("close", 0)
        long_yield = long_data.get("price") or long_data.get("close", 0)
        spread_bp = round((long_yield - short_yield) * 100)  # 转成基点

        inverted = spread_bp < 0
        critical = pair.get("critical_level", 0)

        # 严重程度
        if inverted:
            severity = "critical"
        elif abs(spread_bp) < abs(critical * 100) + 20:
            # 接近临界值 20bp 以内
            severity = "warning"
        else:
            severity = "normal"

        spreads.append({
            "name": pair["name"],
            "short_name": pair["short_key"],
            "long_name": pair["long_key"],
            "short_yield": round(short_yield, 3),
            "long_yield": round(long_yield, 3),
            "spread_bp": spread_bp,
            "inverted": inverted,
            "description": pair["description"],
            "severity": severity,
        })

    return spreads


def format_bond_block(yields: Dict[str, Dict], spreads: List[Dict] = None) -> str:
    """生成债券区块文本"""
    if not yields:
        return ""

    lines = ["【美债收益率曲线】"]
    for _, name, _years in BOND_SYMBOLS:
        q = yields.get(name)
        if not q:
            lines.append(f"  {name:8s}: -")
            continue
        price = q.get("price") or q.get("close", 0)
        pct = q.get("pct", 0)
        lines.append(f"  {name:8s}: {price:>6.3f}% ({pct:+.2f}%)")

    if spreads:
        lines.append("")
        lines.append("  关键利差：")
        for s in spreads:
            icon = {"critical": "🔴", "warning": "🟡", "normal": "🟢"}.get(s["severity"], "•")
            inverted_tag = " ⚠️倒挂" if s["inverted"] else ""
            lines.append(
                f"  {icon} {s['name']}: {s['spread_bp']:+d}bp"
                f"（{s['short_name']} {s['short_yield']:.2f}% / {s['long_name']} {s['long_yield']:.2f}%）{inverted_tag}"
            )

    return "\n".join(lines)


def get_bond_signals(spreads: List[Dict]) -> List[Dict]:
    """把债券曲线异动转成 cross_asset 可用的信号"""
    signals = []
    for s in spreads:
        if s["inverted"]:
            signals.append({
                "name": f"{s['name']} 倒挂",
                "severity": "high",
                "narrative": (
                    f"{s['name']} = {s['spread_bp']:+d}bp（倒挂）\n"
                    f"  {s['description']}\n"
                    "  ↓ 传导：市场定价衰退预期 → 防御性板块（公用事业/医疗/黄金）相对占优，"
                    "周期股/成长股承压"
                ),
                "affected": ["纳斯达克", "创业板指", "沪金主力"],
            })
        elif s["severity"] == "warning" and s["spread_bp"] < 30:
            signals.append({
                "name": f"{s['name']} 收窄至 {s['spread_bp']}bp",
                "severity": "medium",
                "narrative": (
                    f"{s['name']} 仅 {s['spread_bp']:+d}bp，接近倒挂\n"
                    "  ↓ 传导：市场对经济前景谨慎 → 成长股估值空间受限"
                ),
                "affected": ["纳斯达克", "创业板指"],
            })

    # 额外检查：10Y 收益率绝对水平
    y10 = None
    for _, name, _years in BOND_SYMBOLS:
        if name == "美债10Y":
            y10_data = spreads  # not used here
    # 从 yields 取
    ten_y = None
    for s in spreads:
        if s["long_name"] == "美债10Y":
            ten_y = s["long_yield"]
    if ten_y and ten_y >= 4.5:
        signals.append({
            "name": "美债 10Y 突破 4.5%",
            "severity": "high",
            "narrative": (
                f"美债 10Y 收益率达 {ten_y:.2f}%，高于 4.5% 阈值\n"
                "  ↓ 传导：成长股估值压力大（DCF 折现率上升），"
                "黄金机会成本上升 → 金价承压；新兴市场资本外流压力"
            ),
            "affected": ["纳斯达克", "创业板指", "沪金主力"],
        })

    return signals
