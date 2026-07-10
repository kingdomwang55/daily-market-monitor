"""跨资产联动分析（Cross-Asset Signal Engine）

核心目标：把独立的资产异动串联成有因果关系的市场叙事。
不是 AI，是**规则引擎**——AI 分析是下一步，本模块负责给 AI 提供结构化输入。

典型传导链：
1. 就业强 → 收益率升 → 美元强 → 新兴市场撤资 → A股/港股承压
2. 油价跌 → 通胀预期回落 → Fed 降息概率升 → 成长股受益
3. 日元干预 → 美债抛售 → 全球利率联动 → 估值敏感股承压
4. VIX 急升 → 风险偏好回落 → 港股高开低走 / A股权重承压
5. DXY 升 + 黄金跌 + 美债收益率升 → "紧缩交易"组合信号

输入：晨报数据字典（各资产的价格 + 涨跌幅）
输出：结构化信号列表（含逻辑链条、涉及资产、方向）
"""
from typing import List, Dict, Optional, Any


# ── 传导链规则库 ────────────────────────────────────────────
# 每条规则形式：
# {
#     "id": 规则 id,
#     "name": 中文名,
#     "chain": [(资产, 方向, 阈值), ...],  # 所有条件都满足才触发
#     "narrative": lambda data: str,       # 生成叙事文本
#     "affected": [(资产, 方向)],           # 受影响的下游资产（不作触发条件）
# }
#
# 阈值约定：
#   pct >= X → 涨超 X%
#   pct <= -X → 跌超 X%
#   abs(pct) >= X → 波动超 X%

RULES: List[Dict[str, Any]] = [
    {
        "id": "tightening_trade",
        "name": "紧缩交易组合",
        "conditions": [
            ("美元指数", ">=", 0.3),
            ("美债10Y", ">=", 0.02),  # 美债10Y 是收益率，0.02pct = 2bp
        ],
        "narrative": (
            "美元指数走强 + 美债 10Y 收益率上行 → 市场定价『紧缩交易』"
            "（Fed 鹰派 / 强就业 / 通胀韧性预期升温）\n"
            "  ↓ 传导：成长股/黄金/新兴市场承压"
        ),
        "affected": ["纳斯达克", "沪金主力", "上证指数", "创业板指"],
        "severity": "high",
    },
    {
        "id": "risk_off_shock",
        "name": "风险偏好急剧回落",
        "conditions": [
            ("VIX", ">=", 5),  # VIX 单日涨 5% 以上
        ],
        "narrative": (
            "VIX 显著飙升 → 市场恐慌情绪快速抬头\n"
            "  ↓ 传导：美股/港股/A股可能跟随下跌，避险资产（美元/日元/黄金）受追捧"
        ),
        "affected": ["纳斯达克", "恒生指数", "上证指数"],
        "severity": "high",
    },
    {
        "id": "risk_on_rally",
        "name": "风险偏好显著回暖",
        "conditions": [
            ("VIX", "<=", -5),
            ("纳斯达克", ">=", 0.5),
        ],
        "narrative": (
            "VIX 明显回落 + 美股上涨 → 全球风险偏好回暖\n"
            "  ↓ 传导：港股/A股利好开盘，成长股情绪好转"
        ),
        "affected": ["恒生科技", "创业板指"],
        "severity": "medium",
    },
    {
        "id": "oil_disinflation",
        "name": "油价下行 · 通胀预期回落",
        "conditions": [
            ("WTI原油", "<=", -2),
        ],
        "narrative": (
            "原油显著回落 → 通胀预期回落 → Fed 降息概率上升\n"
            "  ↓ 传导：成长股估值扩张空间打开；能源股走弱"
        ),
        "affected": ["纳斯达克", "创业板指"],
        "severity": "medium",
    },
    {
        "id": "oil_supply_shock",
        "name": "原油供给冲击 / 地缘溢价",
        "conditions": [
            ("WTI原油", ">=", 3),
        ],
        "narrative": (
            "原油大幅飙升 → 可能存在地缘冲突或 OPEC 减产 → 通胀韧性回归\n"
            "  ↓ 传导：能源股受益；成长股/新兴市场承压；美元可能走强"
        ),
        "affected": ["上证指数", "纳斯达克"],
        "severity": "high",
    },
    {
        "id": "gold_haven_bid",
        "name": "黄金避险买盘",
        "conditions": [
            ("沪金主力", ">=", 1.5),
            ("VIX", ">=", 3),
        ],
        "narrative": (
            "黄金上涨 + VIX 抬升 → 避险买盘涌入\n"
            "  ↓ 传导：股市风险资产短期承压，黄金/白银受益"
        ),
        "affected": ["上证指数", "恒生指数"],
        "severity": "medium",
    },
    {
        "id": "stagflation_signal",
        "name": "滞胀交易信号",
        "conditions": [
            ("WTI原油", ">=", 1.5),
            ("美债10Y", ">=", 0.03),
            ("纳斯达克", "<=", -0.5),
        ],
        "narrative": (
            "油价 + 美债收益率同时上行 + 美股回落 → 市场担忧滞胀\n"
            "  ↓ 传导：成长股估值双杀（利率↑ + 盈利↓），防御性板块相对占优"
        ),
        "affected": ["纳斯达克", "创业板指"],
        "severity": "high",
    },
    {
        "id": "yuan_pressure",
        "name": "人民币贬值压力",
        "conditions": [
            ("美元指数", ">=", 0.5),
        ],
        "narrative": (
            "美元指数显著走强 → 人民币贬值压力增加\n"
            "  ↓ 传导：A 股外资流出压力上升，港股受承压更明显（联汇制）"
        ),
        "affected": ["上证指数", "恒生指数"],
        "severity": "low",
    },
    {
        "id": "south_flow_bullish",
        "name": "南下资金抄底港股",
        "conditions": [
            ("_south_net", ">=", 50),  # 南下净流入超 50 亿
        ],
        "narrative": (
            "南下资金显著流入（内资看多港股）\n"
            "  ↓ 传导：港股高股息/科技龙头短期支撑增强"
        ),
        "affected": ["恒生指数", "恒生科技"],
        "severity": "medium",
    },
    {
        "id": "south_flow_bearish",
        "name": "南下资金撤退",
        "conditions": [
            ("_south_net", "<=", -30),
        ],
        "narrative": (
            "南下资金显著流出 → 内资撤退港股\n"
            "  ↓ 传导：港股短期承压，A 股同板块（金融/科技）也可能被拖累"
        ),
        "affected": ["恒生指数", "上证指数"],
        "severity": "medium",
    },
]


# ── 条件评估 ────────────────────────────────────────────────

def _get_pct(data: Dict, key: str) -> Optional[float]:
    """从晨报数据字典里取 pct 字段。

    支持:
    - data['纳斯达克'] = {'pct': 0.5} → 0.5
    - data['_south_latest'] = {'net': 60} → 用 _south_net key
    """
    if key == "_south_net":
        south = data.get("_south_latest")
        if south:
            return south.get("net")
        return None
    d = data.get(key)
    if d is None:
        return None
    if isinstance(d, dict):
        return d.get("pct") or d.get("change_pct")
    return None


def _check_condition(data: Dict, asset: str, op: str, threshold: float) -> bool:
    """检查一个条件是否满足"""
    val = _get_pct(data, asset)
    if val is None:
        return False
    if op == ">=":
        return val >= threshold
    if op == "<=":
        return val <= threshold
    if op == ">":
        return val > threshold
    if op == "<":
        return val < threshold
    if op == "abs>=":
        return abs(val) >= threshold
    return False


def _rule_matches(data: Dict, rule: Dict) -> bool:
    """所有条件都满足才触发"""
    for asset, op, threshold in rule["conditions"]:
        if not _check_condition(data, asset, op, threshold):
            return False
    return True


# ── 主入口 ────────────────────────────────────────────────

def analyze(data: Dict) -> List[Dict]:
    """跨资产联动分析。

    Args:
        data: 晨报数据字典（各资产名 → {price, pct, ...}）

    Returns:
        触发的信号列表：
        [
            {
                "id": "tightening_trade",
                "name": "紧缩交易组合",
                "severity": "high",
                "narrative": "...",
                "affected": ["纳斯达克", "沪金主力"],
                "triggering_data": [
                    ("美元指数", 0.35),
                    ("美债10Y", 0.05),
                ],
            },
            ...
        ]
    """
    signals = []
    for rule in RULES:
        if not _rule_matches(data, rule):
            continue
        triggering = []
        for asset, op, thr in rule["conditions"]:
            val = _get_pct(data, asset)
            if val is not None:
                triggering.append((asset, round(val, 2)))
        signals.append({
            "id": rule["id"],
            "name": rule["name"],
            "severity": rule.get("severity", "medium"),
            "narrative": rule["narrative"],
            "affected": rule.get("affected", []),
            "triggering_data": triggering,
        })
    return signals


def format_signals(signals: List[Dict]) -> str:
    """把信号列表格式化为人类可读文本（用在晨报里）"""
    if not signals:
        return "（本次数据未触发跨资产传导信号）"

    # 按严重程度排序
    order = {"high": 0, "medium": 1, "low": 2}
    signals = sorted(signals, key=lambda s: order.get(s["severity"], 3))

    icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    lines = []
    for s in signals:
        icon = icons.get(s["severity"], "•")
        lines.append(f"{icon} 【{s['name']}】")
        # 触发条件
        trig_parts = []
        for a, v in s["triggering_data"]:
            if a == "_south_net":
                trig_parts.append(f"南下资金 {v:+.2f} 亿")
            else:
                trig_parts.append(f"{a} {v:+.2f}%")
        lines.append(f"  触发：{' · '.join(trig_parts)}")
        # 叙事
        for line in s["narrative"].split("\n"):
            lines.append(f"  {line}")
        lines.append("")

    return "\n".join(lines).rstrip()


def signals_summary_for_ai(signals: List[Dict]) -> str:
    """给 AI 看的紧凑版（省 token）"""
    if not signals:
        return "跨资产传导信号：本次无显著触发"
    parts = ["跨资产传导信号（规则引擎检测）："]
    for s in signals:
        trig = ", ".join(
            (f"南下资金={v:+.2f}亿" if a == "_south_net" else f"{a}={v:+.2f}%")
            for a, v in s["triggering_data"]
        )
        parts.append(f"- [{s['severity']}] {s['name']} | 触发条件: {trig} | 影响: {', '.join(s['affected'])}")
    return "\n".join(parts)
