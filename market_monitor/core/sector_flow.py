"""板块资金流分析（P2-1）

数据源：东方财富板块行情 + 主力资金流 API
- 行业板块（fs=m:90+t:2）
- 概念板块（fs=m:90+t:3，作为增强）

核心接口：
- fetch_sector_flow(kind="industry"|"concept", top_n=50) -> List[Dict]
- format_sector_flow(items, top=5) -> str  # 给人看
- sector_flow_summary_for_ai(items) -> str  # 给 AI 看
- analyze_sector_rotation(items) -> List[Dict]  # 输出结构化轮动/资金异动信号
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from typing import Dict, List, Optional

# 字段说明：
# f12 = 代码
# f14 = 名称
# f3  = 涨跌幅 (%)
# f62 = 主力净流入 (元)
# f184= 主力净流入占比 (%)
# f66 = 超大单净流入 (元)
# f72 = 大单净流入 (元)
# f204/f205 = 龙头股名/涨跌幅
_FIELDS = "f12,f14,f3,f62,f184,f66,f72,f204,f205"

_FS_MAP = {
    "industry": "m:90+t:2",  # 行业板块
    "concept": "m:90+t:3",   # 概念板块
}

# 板块资金流 API 阈值（元）
NET_INFLOW_LARGE = 10_0000_0000  # 10 亿：显著流入
NET_INFLOW_HUGE = 50_0000_0000   # 50 亿：巨额流入
NET_OUTFLOW_LARGE = -10_0000_0000
NET_OUTFLOW_HUGE = -50_0000_0000

# 主力占比阈值（%）
RATIO_STRONG = 5.0     # 主力净流入占比 > 5% 强
RATIO_VERY_STRONG = 10.0

# 涨跌幅阈值（%）
PCT_STRONG = 3.0


def fetch_sector_flow(kind: str = "industry", top_n: int = 50,
                      timeout: int = 8, retries: int = 3) -> List[Dict]:
    """拉取板块资金流。

    Args:
        kind: industry / concept
        top_n: 返回前 N 个（按主力净流入降序）
        retries: 网络失败重试次数
    Returns:
        List of dict with keys: code, name, pct, net_inflow, net_ratio,
                                huge_order, big_order, leader, leader_pct
    """
    fs = _FS_MAP.get(kind)
    if not fs:
        return []

    url = (
        f"https://push2.eastmoney.com/api/qt/clist/get?"
        f"pn=1&pz={top_n}&po=1&np=1&fltt=2&invt=2&fid=f62"
        f"&fs={fs}&fields={_FIELDS}"
    )
    headers = {
        "Referer": "https://quote.eastmoney.com/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15",
        "Accept": "*/*",
    }

    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8")
            j = json.loads(raw)
            items = j.get("data", {}).get("diff", []) or []
            result: List[Dict] = []
            for it in items:
                try:
                    result.append({
                        "code": it.get("f12"),
                        "name": it.get("f14"),
                        "pct": _f(it.get("f3")),
                        "net_inflow": _f(it.get("f62")),
                        "net_ratio": _f(it.get("f184")),
                        "huge_order": _f(it.get("f66")),
                        "big_order": _f(it.get("f72")),
                        "leader": it.get("f204"),
                        "leader_pct": _f(it.get("f205")),
                    })
                except (TypeError, ValueError):
                    continue
            return result
        except Exception as e:  # noqa: BLE001
            last_err = e
            if attempt < retries - 1:
                time.sleep(0.6 * (attempt + 1))

    print(f"[sector_flow] {kind} 拉取失败({retries} 次): {last_err}", file=sys.stderr)
    return []


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _fmt_yi(net: float) -> str:
    """元 → 亿"""
    return f"{net/1e8:+.2f}亿"


# ------------------------- 展示格式化 -------------------------
def format_sector_flow(items: List[Dict], top: int = 5, kind_label: str = "行业") -> str:
    """给人看：主力净流入 top/bottom 各 N 个。"""
    if not items:
        return f"（{kind_label}板块资金流数据缺失）"

    # items 已按主力净流入降序（API fid=f62）
    inflow = items[:top]
    outflow = sorted(items, key=lambda x: x["net_inflow"])[:top]

    lines = []
    lines.append(f"💰 主力净流入 Top{top}:")
    for i, it in enumerate(inflow, 1):
        leader = f" 龙头:{it['leader']}({it['leader_pct']:+.2f}%)" if it.get("leader") else ""
        lines.append(
            f"  {i}. {it['name']:<10} {it['pct']:+.2f}% "
            f"主力={_fmt_yi(it['net_inflow'])} 占比={it['net_ratio']:+.2f}%{leader}"
        )
    lines.append("")
    lines.append(f"💸 主力净流出 Top{top}:")
    for i, it in enumerate(outflow, 1):
        lines.append(
            f"  {i}. {it['name']:<10} {it['pct']:+.2f}% "
            f"主力={_fmt_yi(it['net_inflow'])} 占比={it['net_ratio']:+.2f}%"
        )
    return "\n".join(lines)


# ------------------------- AI 摘要 -------------------------
def sector_flow_summary_for_ai(items: List[Dict], top: int = 8) -> str:
    """给 AI 看：简洁列表，便于叙事分析。"""
    if not items:
        return "（板块资金流数据缺失，无法分析板块轮动）"

    inflow = items[:top]
    outflow = sorted(items, key=lambda x: x["net_inflow"])[:top]

    lines = ["【板块资金流】"]
    lines.append("主力净流入板块（当日）:")
    for it in inflow:
        lines.append(
            f"- {it['name']} {it['pct']:+.2f}% "
            f"主力{_fmt_yi(it['net_inflow'])} 占比{it['net_ratio']:+.2f}%"
        )
    lines.append("主力净流出板块（当日）:")
    for it in outflow:
        lines.append(
            f"- {it['name']} {it['pct']:+.2f}% 主力{_fmt_yi(it['net_inflow'])}"
        )
    return "\n".join(lines)


# ------------------------- 结构化信号引擎 -------------------------
def analyze_sector_rotation(items: List[Dict]) -> List[Dict]:
    """从当日板块资金流数据中识别关键信号。

    返回 signal dict，字段与 cross_asset.py 保持一致：
        id / name / severity / narrative / affected / triggering_data
    """
    if not items:
        return []

    signals: List[Dict] = []

    # 排序
    by_inflow = items[:]  # API 已按 f62 降序
    by_outflow = sorted(items, key=lambda x: x["net_inflow"])
    by_pct_up = sorted(items, key=lambda x: -x["pct"])
    by_pct_down = sorted(items, key=lambda x: x["pct"])

    top1 = by_inflow[0]

    # ---------- 信号 1：主力扫货某板块（超强流入 + 强上涨） ----------
    if (top1["net_inflow"] >= NET_INFLOW_HUGE
            and top1["net_ratio"] >= RATIO_STRONG
            and top1["pct"] >= PCT_STRONG):
        signals.append({
            "id": "sector_hot_money_rush",
            "name": "主力扫货集中板块",
            "severity": "high",
            "narrative": (
                f"『{top1['name']}』主力净流入 {_fmt_yi(top1['net_inflow'])}"
                f"（占比 {top1['net_ratio']:+.2f}%），板块涨幅 {top1['pct']:+.2f}%\n"
                f"  ↓ 判断：机构资金明显抱团/追高进场；短线情绪高但注意追高风险，龙头 {top1.get('leader','?')} "
                f"({top1.get('leader_pct', 0):+.2f}%) 可作情绪风向标"
            ),
            "affected": [top1["name"]],
            "triggering_data": [
                (top1["name"], top1["net_inflow"], top1["net_ratio"], top1["pct"]),
            ],
        })

    # ---------- 信号 2：板块跳水 & 主力砸盘 ----------
    worst = by_outflow[0]
    if worst["net_inflow"] <= NET_OUTFLOW_LARGE and worst["pct"] <= -PCT_STRONG:
        signals.append({
            "id": "sector_capitulation",
            "name": "板块砸盘出逃",
            "severity": "high",
            "narrative": (
                f"『{worst['name']}』主力净流出 {_fmt_yi(worst['net_inflow'])}"
                f"，板块跌 {worst['pct']:+.2f}%\n"
                f"  ↓ 判断：机构主动减仓；若为前期热点则警惕情绪拐点，若持有相关个股建议规避或减仓"
            ),
            "affected": [worst["name"]],
            "triggering_data": [
                (worst["name"], worst["net_inflow"], worst["pct"]),
            ],
        })

    # ---------- 信号 3：板块轮动信号（涨幅榜前 5 主力流入>0 的板块统一叙事） ----------
    hot_leaders = [
        it for it in by_pct_up[:5]
        if it["net_inflow"] > 0 and it["pct"] >= 2.0
    ]
    cold_leaders = [
        it for it in by_pct_down[:5]
        if it["net_inflow"] < 0 and it["pct"] <= -2.0
    ]
    if len(hot_leaders) >= 3 and len(cold_leaders) >= 3:
        hot_names = [it["name"] for it in hot_leaders[:3]]
        cold_names = [it["name"] for it in cold_leaders[:3]]
        signals.append({
            "id": "sector_rotation",
            "name": "板块轮动明显",
            "severity": "medium",
            "narrative": (
                f"资金从 {'/'.join(cold_names)} 撤离，转向 {'/'.join(hot_names)}\n"
                f"  ↓ 判断：市场风格切换（或高低切）；持仓可考虑向流入板块调整，但注意验证 2-3 日趋势再决策"
            ),
            "affected": hot_names + cold_names,
            "triggering_data": [
                *[(it["name"], it["net_inflow"], it["pct"]) for it in hot_leaders[:3]],
                *[(it["name"], it["net_inflow"], it["pct"]) for it in cold_leaders[:3]],
            ],
        })

    # ---------- 信号 4：普跌但主力流出集中 ----------
    total_outflow = sum(it["net_inflow"] for it in items if it["net_inflow"] < 0)
    down_count = sum(1 for it in items if it["pct"] < 0)
    if down_count >= len(items) * 0.7 and total_outflow <= NET_OUTFLOW_HUGE * 3:
        signals.append({
            "id": "sector_broad_selloff",
            "name": "板块普跌资金撤离",
            "severity": "high",
            "narrative": (
                f"{down_count}/{len(items)} 板块下跌，全市主力净流出 {_fmt_yi(total_outflow)}\n"
                f"  ↓ 判断：系统性风险偏好回落；防御性板块（消费/公用事业/黄金）相对占优，"
                f"高 beta 成长股承压"
            ),
            "affected": ["全市场"],
            "triggering_data": [
                ("下跌板块数", down_count, len(items)),
                ("全市主力净流出", total_outflow, 0.0),
            ],
        })

    # ---------- 信号 5：抗跌板块（大盘弱势但仍有大额净流入） ----------
    if down_count >= len(items) * 0.6:
        defensive = [
            it for it in items
            if it["net_inflow"] >= NET_INFLOW_LARGE and it["pct"] > 0
        ][:3]
        if defensive:
            names = [it["name"] for it in defensive]
            signals.append({
                "id": "sector_defensive_bid",
                "name": "弱势中的资金避风港",
                "severity": "medium",
                "narrative": (
                    f"大盘弱势（{down_count}/{len(items)} 板块下跌）但 "
                    f"{'/'.join(names)} 逆势获主力增仓\n"
                    f"  ↓ 判断：结构性机会/防御主线；观察 2-3 日验证是否形成新的资金主线"
                ),
                "affected": names,
                "triggering_data": [
                    (it["name"], it["net_inflow"], it["pct"]) for it in defensive
                ],
            })

    return signals


def format_sector_signals(signals: List[Dict]) -> str:
    """把 sector 信号渲染成人类可读格式。"""
    if not signals:
        return "（本次板块数据未触发资金流轮动信号）"
    icons = {"high": "🚨", "medium": "⚠️", "low": "💡"}
    lines = ["🏭 板块资金流传导信号:"]
    for s in signals:
        lines.append("")
        lines.append(f"{icons.get(s['severity'], '•')} 【{s['name']}】")
        lines.append(s["narrative"])
    return "\n".join(lines)


def sector_signals_summary_for_ai(signals: List[Dict]) -> str:
    """把 sector 信号打包成 AI prompt 段。"""
    if not signals:
        return "（板块资金流：未触发轮动/异动信号）"
    lines = ["【板块资金流信号】"]
    for s in signals:
        lines.append(f"- [{s['id']}] {s['name']} ({s['severity']}): "
                     f"{s['narrative'].splitlines()[0]}")
    return "\n".join(lines)
