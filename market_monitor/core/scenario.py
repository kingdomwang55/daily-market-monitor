"""情景推演模板（P2-3）

针对高影响事件（FOMC/CPI/PPI/PMI/就业/地缘突发），
预设"鸽/中性/鹰"三档市场反应模板，供 AI 分析时参考。

核心接口：
- get_scenario(event_title: str, event_impact: str) -> Optional[Dict]
  匹配已知事件，返回模板
- match_scenario_by_keyword(title: str) -> Optional[Dict]
  模糊匹配事件标题
- format_scenario_for_ai(scenario: Dict) -> str
  格式化为 AI prompt 段
- get_all_templates() -> List[Dict]
  列出所有模板

每个模板结构：
{
    "id": str,
    "event_keywords": List[str],   # 匹配关键词
    "event_label": str,            # 显示名
    "importance": int,             # 5 最高
    "dove": {                      # 鸽派/低于预期
        "narrative": str,
        "market_impact": str,
        "sectors": List[str],      # 受益/承压板块
    },
    "neutral": { ... },
    "hawk": { ... },               # 鹰派/高于预期
}
"""
from __future__ import annotations

from typing import Dict, List, Optional

# ---------- 模板库 ----------
_TEMPLATES: List[Dict] = [
    # ========== 美联储利率决议 ==========
    {
        "id": "fomc_rate",
        "event_keywords": ["FOMC", "美联储", "fed rate", "fed funds", "利率决议", "federal reserve"],
        "event_label": "美联储利率决议",
        "importance": 5,
        "dove": {
            "narrative": "降息 / 比预期更鸽派（点阵图下移 / 降息预期前置）",
            "market_impact": (
                "✅ 美股（尤其科技/成长股）大涨，美债收益率下行，美元走弱\n"
                "✅ 黄金/白银走强，新兴市场（含 A 股）资金回流\n"
                "✅ 港股受益于弱美元 + 资金回流"
            ),
            "sectors": ["科技", "半导体", "消费电子", "黄金", "港股科技"],
        },
        "neutral": {
            "narrative": "按预期降/加息 25bp，措辞中性",
            "market_impact": (
                "• 短期波动后回归基本面\n"
                "• 美股/美债/美元维持原有趋势\n"
                "• 市场焦点转向下一次会议指引"
            ),
            "sectors": [],
        },
        "hawk": {
            "narrative": "暂停降息 / 比预期更鹰（点阵图上移 / 降息预期推迟）",
            "market_impact": (
                "❌ 美股（尤其科技/成长股）承压，美债收益率飙升，美元走强\n"
                "❌ 黄金回调，新兴市场资金流出\n"
                "❌ 港股/北向资金承压，人民币贬值压力增大"
            ),
            "sectors": ["银行（受益于高息环境）", "公用事业（防御）", "防御性消费"],
        },
    },
    # ========== CPI 数据 ==========
    {
        "id": "cpi_us",
        "event_keywords": ["CPI", "消费者物价指数", "consumer price", "通胀"],
        "event_label": "美国 CPI 数据",
        "importance": 5,
        "dove": {
            "narrative": "CPI 低于预期（通胀降温）",
            "market_impact": (
                "✅ 降息预期升温，美股/美债走强，美元走弱\n"
                "✅ 黄金/白银上涨，成长股/科技股领涨\n"
                "✅ A 股/港股外部压力减轻，外资回流"
            ),
            "sectors": ["科技", "半导体", "消费电子", "地产", "黄金"],
        },
        "neutral": {
            "narrative": "CPI 符合预期，核心通胀仍偏高",
            "market_impact": (
                "• 市场反应平淡，维持现有降息路径\n"
                "• 短端美债收益率小幅波动\n"
                "• 关注其他分项（住房/服务）趋势"
            ),
            "sectors": [],
        },
        "hawk": {
            "narrative": "CPI 高于预期（通胀顽固）",
            "market_impact": (
                "❌ 降息预期推迟，美债收益率飙升，美元走强\n"
                "❌ 美股科技/成长股大跌，纳指领跌\n"
                "❌ 黄金回调，A 股/港股外部压力增大\n"
                "❌ 人民币汇率承压，北向资金可能流出"
            ),
            "sectors": ["银行（高息利好）", "能源（油价传导）", "必需消费（防御）"],
        },
    },
    # ========== 中国 CPI/PPI ==========
    {
        "id": "cpi_ppi_cn",
        "event_keywords": ["CPI", "PPI", "中国通胀", "居民消费价格", "工业生产者"],
        "event_label": "中国 CPI/PPI 数据",
        "importance": 4,
        "dove": {
            "narrative": "CPI 温和/PPI 回升（通缩压力缓解）",
            "market_impact": (
                "✅ 政策预期改善（降准/降息空间打开）\n"
                "✅ 内需相关板块受益\n"
                "✅ 人民币企稳"
            ),
            "sectors": ["消费", "白酒", "医药", "地产"],
        },
        "neutral": {
            "narrative": "CPI 低位徘徊，PPI 小幅波动",
            "market_impact": (
                "• 市场反应有限，延续存量博弈\n"
                "• 通缩预期仍在，等待更大力度的财政/货币政策"
            ),
            "sectors": [],
        },
        "hawk": {
            "narrative": "CPI 意外走高（滞胀担忧）",
            "market_impact": (
                "❌ 政策空间受限，市场对经济担忧加剧\n"
                "❌ 消费股承压，必需消费相对抗跌\n"
                "❌ 债券收益率上行"
            ),
            "sectors": ["必需消费", "公用事业", "能源"],
        },
    },
    # ========== 非农就业 ==========
    {
        "id": "nonfarm_payrolls",
        "event_keywords": ["非农", "就业", "payrolls", "unemployment", "失业率", "NFP", "nonfarm"],
        "event_label": "美国非农就业数据",
        "importance": 5,
        "dove": {
            "narrative": "就业低于预期（经济降温）",
            "market_impact": (
                "✅ 降息预期升温，美债收益率下行\n"
                "✅ 科技/成长股受益\n"
                "✅ 黄金走强"
            ),
            "sectors": ["科技", "黄金", "美债"],
        },
        "neutral": {
            "narrative": "就业符合预期，失业率稳定",
            "market_impact": (
                "• 市场按原有趋势运行\n"
                "• 关注时薪增速和劳动参与率"
            ),
            "sectors": [],
        },
        "hawk": {
            "narrative": "就业强劲超预期（劳动力市场过热）",
            "market_impact": (
                "❌ 降息预期推迟，美债收益率飙升\n"
                "❌ 美元走强，新兴市场/人民币承压\n"
                "❌ 成长股承压，价值/周期股相对抗跌"
            ),
            "sectors": ["银行", "能源", "工业", "价值股"],
        },
    },
    # ========== PMI 数据 ==========
    {
        "id": "pmi_global",
        "event_keywords": ["PMI", "采购经理人指数", "制造业", "服务业", "ISM", "purchasing managers"],
        "event_label": "PMI 数据",
        "importance": 4,
        "dove": {
            "narrative": "PMI 低于 50 且超预期下行（经济衰退信号）",
            "market_impact": (
                "✅ 降息预期升温，避险资产走强\n"
                "✅ 防御性板块（公用事业/医药/消费）相对占优\n"
                "❌ 周期股（工业/原材料/能源）承压"
            ),
            "sectors": ["公用事业", "医药", "必需消费", "黄金"],
        },
        "neutral": {
            "narrative": "PMI 在 50 荣枯线附近窄幅波动",
            "market_impact": (
                "• 经济方向不明，市场维持震荡格局\n"
                "• 关注新订单和就业分项"
            ),
            "sectors": [],
        },
        "hawk": {
            "narrative": "PMI 扩张超预期（经济过热/通胀压力）",
            "market_impact": (
                "✅ 周期股/工业/原材料受益\n"
                "❌ 降息预期降温，美债收益率上行\n"
                "❌ 成长股估值承压"
            ),
            "sectors": ["工业", "原材料", "能源", "银行"],
        },
    },
    # ========== 地缘突发事件 ==========
    {
        "id": "geo_shock",
        "event_keywords": ["军事冲突", "战争", "空袭", "轰炸", "导弹", "military", "war", "strike",
                           "invasion", "terror", "attack", "报复"],
        "event_label": "地缘军事突发事件",
        "importance": 5,
        "dove": {
            "narrative": "事件快速平息 / 谈判取得进展",
            "market_impact": (
                "✅ 风险偏好快速修复\n"
                "✅ 此前受压的资产（风险资产/EM）反弹\n"
                "❌ 避险资产（黄金/美债/日元）回落"
            ),
            "sectors": ["科技（超跌反弹）", "消费（情绪修复）", "航空"],
        },
        "neutral": {
            "narrative": "事件按预期发展，无重大升级",
            "market_impact": (
                "• 市场已部分定价，后续影响有限\n"
                "• 关注后续制裁/反制措施"
            ),
            "sectors": [],
        },
        "hawk": {
            "narrative": "事件升级 / 扩大化（全面冲突/制裁升级）",
            "market_impact": (
                "❌ 全球风险偏好骤降，避险资产暴涨\n"
                "✅ 黄金/美元/日元/美债（避险资金涌入）\n"
                "✅ 能源/军工/黄金股受益\n"
                "❌ A 股/港股/EM 大幅承压\n"
                "❌ 供应链扰动 → 相关板块波动"
            ),
            "sectors": ["黄金", "军工", "能源", "航运", "农产品"],
        },
    },
]


# ---------- 匹配逻辑 ----------
def match_scenario_by_keyword(title: str) -> Optional[Dict]:
    """模糊匹配事件标题，返回最匹配的模板。"""
    t = title.lower()
    best: Optional[Dict] = None
    best_score = 0
    for tmpl in _TEMPLATES:
        score = 0
        for kw in tmpl["event_keywords"]:
            if kw.lower() in t:
                # 关键词越长，匹配越精准
                score += len(kw)
        if score > best_score:
            best_score = score
            best = tmpl
    # 至少匹配 2 个字符才算命中
    return best if best_score >= 2 else None


def get_scenario(event_title: str, event_impact: str = "") -> Optional[Dict]:
    """根据事件标题 + 影响等级，返回匹配的模板。

    Args:
        event_title: 事件标题（如 "FOMC Meeting Minutes"）
        event_impact: 影响等级（"High"/"Medium"/"Low"）
    Returns:
        匹配的模板 dict，或 None
    """
    return match_scenario_by_keyword(event_title)


def get_all_templates() -> List[Dict]:
    """返回所有模板。"""
    return list(_TEMPLATES)


# ---------- 格式化 ----------
def format_scenario_for_ai(scenario: Dict, outlook: str = "neutral") -> str:
    """将单个情景模板格式化为 AI prompt 段。

    Args:
        scenario: 模板 dict
        outlook: 预期方向（dove / neutral / hawk）
    Returns:
        格式化字符串
    """
    label = scenario["event_label"]
    imp = scenario["importance"]
    s = scenario.get(outlook, scenario.get("neutral", scenario["dove"]))
    return (
        f"【情景推演：{label} (重要性{'⭐' * imp})】\n"
        f"预期场景：{outlook}\n"
        f"叙事：{s['narrative']}\n"
        f"市场影响：\n{s['market_impact']}\n"
        f"关联板块：{', '.join(s['sectors']) if s['sectors'] else '无特定板块'}"
    )


def format_scenarios_for_calendar(calendar_events: List[Dict]) -> str:
    """将日历事件中的高影响事件匹配到情景模板，输出 AI 段。

    Args:
        calendar_events: 日历事件列表（含 title, impact, impact_score 等字段）
    Returns:
        格式化字符串
    """
    matched = []
    for ev in calendar_events:
        tmpl = match_scenario_by_keyword(ev.get("title", ""))
        if tmpl:
            matched.append((ev, tmpl))

    if not matched:
        return ""

    lines = ["【情景推演模板（高影响事件预期）】"]
    for ev, tmpl in matched:
        title = ev.get("title", tmpl["event_label"])
        imp = tmpl["importance"]
        lines.append(f"\n📌 {title} (重要性{'⭐' * imp})")
        lines.append(f"  鸽派：{tmpl['dove']['narrative']}")
        lines.append(f"  中性：{tmpl['neutral']['narrative']}")
        lines.append(f"  鹰派：{tmpl['hawk']['narrative']}")
    return "\n".join(lines)