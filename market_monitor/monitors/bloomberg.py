"""Bloomberg 发文言论监控（Phase 1）

监控 Bloomberg 彭博社的主要发文/报道/观点，每日两推：
- 🕖 早上 08:10（开市前）：回溯 24h，覆盖前夜美股盘后到今早的全球重磅
- 🕛 中午 12:00（下午开市前）：回溯 12h，覆盖上午亚洲时段 + 欧盘初

模板参考 voice_monitor + macro_monitor 的 AI 分析模式。
"""
import re
from datetime import datetime
from typing import List, Dict

from ..core.base import BaseMonitor
from ..core.bloomberg_sources import fetch_by_category, CATEGORY_LABELS
from ..core.ai import ai_chat
from ..core.teaching import get_daily_tip


# 每类最多送 AI 的条数
MAX_PER_CATEGORY = {
    "markets":   15,
    "politics":  10,
    "tech":      10,
    "economics": 10,
    "opinion":   10,
}

# 两个时段配置
TIME_SLOTS = {
    "morning": {
        "label": "开市前 · 昨夜今晨",
        "hours": 24,
        "slot_key_prefix": "bloomberg_morning",
    },
    "midday": {
        "label": "午间 · 上午动态",
        "hours": 12,
        "slot_key_prefix": "bloomberg_midday",
    },
}


class BloombergMonitor(BaseMonitor):
    name = "bloomberg"
    display_name = "彭博发文日报"

    def _current_slot(self) -> tuple:
        """根据当前时间判断是 morning 还是 midday 时段"""
        hour = self.now.hour
        if 7 <= hour < 10:
            slot_name = "morning"
        elif 11 <= hour < 14:
            slot_name = "midday"
        else:
            # 非推送时段，默认 morning（run 时会被防重发拦截）
            slot_name = "morning"
        cfg = TIME_SLOTS[slot_name]
        return slot_name, cfg["label"], cfg["hours"], cfg["slot_key_prefix"]

    def _build_raw_section(self, data: Dict[str, List[Dict]]) -> str:
        """给 AI 看的原始文章列表"""
        lines = []
        for cat, items in data.items():
            label = CATEGORY_LABELS.get(cat, cat)
            batch = items[:MAX_PER_CATEGORY.get(cat, 15)]
            if not batch:
                lines.append(f"\n== {label}（无新文章）==")
                continue
            lines.append(f"\n== {label}（{len(batch)} 条）==")
            for it in batch:
                author = f" 👤 {it['author']}" if it.get('author') else ""
                lines.append(f"[{it['timestamp']}] {it['text'][:150]}{author}")
                if it.get("summary") and len(it["summary"]) > 10:
                    lines.append(f"  → {it['summary'][:120]}")
        return "\n".join(lines)

    def _build_ai_prompt(self, data: Dict[str, List[Dict]],
                         slot_label: str, hours: int) -> str:
        raw = self._build_raw_section(data)
        today = datetime.now().strftime("%Y-%m-%d %A")

        return f"""你是一位资深全球宏观/美股分析师，专精"彭博社发文 → 市场影响"的联动分析。

下面是过去 {hours} 小时彭博社 Bloomberg 的报道/观点汇总。当前时段：{slot_label}。

彭博社是华尔街最权威的财经媒体，其报道方向、观点倾向、对特定话题的密集覆盖，往往能预示市场风向。彭博最大的独家价值在于"知情人爆料"——通过匿名信源提前披露未公开信息，这对市场冲击最大。

请完成两件事：

【第一步】重要性打分（仅内部思考，不要输出打分过程！）
对每条文稿打 1-10 分（10 = 可能引发市场 3%+ 波动），只保留 ≥ 7 分的。
打分维度：
- 涉及 Fed 政策/利率/通胀/就业 → 加分
- 涉及关税/贸易战/地缘冲突 → 加分
- 涉及大公司财报/并购/新品 → 加分
- 涉及原油/黄金/美元等核心资产 → 加分
- 涉及中国政策/监管/经济数据/人民币/港股 → 加分
- 涉及中概股/中国科技公司/中国互联网 → 强加分
- 涉及中美关系/关税/供应链脱钩/科技竞争 → 强加分
- 涉及中东/俄乌/台海等 → 加分
- Opinion 观点栏目的重磅文章（标题有"专栏"、"观点"感）→ 加分
- ⚡ 文章包含"people familiar" / "知情人士" / "sources say" / "disclosed" / "leaked" / "reveals" 等知情人爆料特征 → 强加分（彭博核心价值！）
- ⚡ 涉及未公开信息/内幕/提前泄露/谈判进展/政策草案 → 强加分
- 纯公司常规新闻/个股涨跌 → 减分
- 区域性小新闻（拉美/非洲/欧洲地方政治）→ 减分

【第二步】直接输出日报

⚠⚠⚠ 最重要的输出规则（违反任意一条都是严重错误）：

【禁止使用任何 Markdown 符号】
❌ 不要使用 # 或 ## 或 ### 作为标题（使用【】代替）
❌ 不要使用 ** 或 __ 做加粗
❌ 不要使用 --- 或 === 做分割线
❌ 不要使用 | ... | 表格结构
❌ 不要使用 * 或 - 开头的列表（直接写句子即可）
❌ 不要写"第一步：重要性打分"这种内部思考过程
❌ 不要使用 ``` 代码块

【必须遵守的格式】
✅ 按分类分段，标题固定用【】包裹：
   【{CATEGORY_LABELS.get('markets', '🏛️ 市场')}】
   【{CATEGORY_LABELS.get('politics', '🏛️ 政策/地缘')}】
   【{CATEGORY_LABELS.get('tech', '🏛️ 科技')}】
   【{CATEGORY_LABELS.get('economics', '🏛️ 经济/央行')}】
   【{CATEGORY_LABELS.get('opinion', '📰 观点/分析')}】
✅ 每条固定格式：
   [时间] 文章标题摘要（≤ 60 字）
   → 影响：涉及xxx
   📊 关联标的：SPY / 黄金 / 原油 / TSLA / 上证
   👤 作者：xxx（如果有）
✅ 该段无 ≥ 7 分的文章 → 写"（无重要文章）"
✅ 额外增加一段【🔍 知情人爆料】（放在观点段之后，中国相关段之前）：
   - 从所有文章中筛选包含"知情人/爆料/独家来源"特征的文章
   - 关键词：people familiar / 知情人士 / sources say / disclosed / leak / confidential / secret / internal / memo / leaked /私下/提前/即将宣布/独家/独家报道
   - 门槛降低到 ≥ 6 分即可纳入（爆料类天然高价值）
   - 每条同样格式：[时间]标题摘要 → 影响 → 📊 关联标的 → 👤 作者
   - 如果完全没有爆料类文章，写"（无重要爆料）"
   - 这段放在观点段之后，中国相关段之前
✅ 额外增加一段【🇨🇳 中国相关】（独立于上面几段之外，放在爆料段之后）：
   - 从所有文章中筛选与中国/A股/港股/中概股相关的文章
   - 门槛降低到 ≥ 6 分即可纳入（对中国市场影响大，宽松门槛）
   - 每条同样格式：[时间]标题摘要 → 影响 → 📊 关联标的
   - 如果完全没有中国相关的重要文章，写"（无重要中国相关文章）"
   - 这段放在爆料段之后，综合观察段之前
✅ 末尾【🎯 综合观察】一段总结 Bloomberg 今日的报道方向和市场信号
   - 务必包含对中国市场/中概股的影响判断
   - 如果发现 Bloomberg 对中国有密集负面/正面报道，需特别指出"密集偏空"或"密集偏多"
   - 如有知情人爆料内容，需单独评价"爆料可信度/市场冲击"
✅ 中文，总字数 600-900 字
✅ 直接从【{CATEGORY_LABELS.get('markets', '🏛️ 市场')}】开始写，不要任何前置说明

【正确示例】
【🏛️ 市场】
[07-22 06:07] 美股收跌，伊朗冲突升级推高油价至$95
→ 影响：地缘风险压制风险偏好
📊 关联标的：SPY / 原油
👤 Rita Nazareth

【🔍 知情人爆料】
[07-22 14:00] 知情人士：苹果正洽谈收购AI初创公司
→ 影响：涉及科技巨头AI布局
📊 关联标的：AAPL

【📰 观点/分析】
[07-21 12:00] 关于24/7全天候石油交易的争议性观点
→ 影响：涉及交易基础设施变革
📊 关联标的：原油期货

【错误示例（千万不要）】
## 第一步：打分
**Markets**：
| 时间 | 文章 | 分数 |

彭博文章数据：
{raw}

今天日期：{today}
"""

    def _format_report(self, data: Dict[str, List[Dict]],
                       analysis: str, slot_label: str, hours: int) -> str:
        """组装最终推送文本"""
        parts = [
            f"📰 彭博社发文日报",
            f"📅 {self.now_str} · {slot_label}（回溯 {hours}h）",
            "",
        ]

        # 数据统计
        summary_parts = []
        for cat in ["markets", "politics", "tech", "economics", "opinion"]:
            n = len(data.get(cat, []))
            label = CATEGORY_LABELS[cat].split(" ", 1)[1]
            summary_parts.append(f"{label} {n}")
        parts.append(f"📊 文章数：{' · '.join(summary_parts)}")
        parts.append("")

        if analysis:
            parts.append("━━━━━━━━━━━━━━━")
            parts.append(analysis)
        else:
            parts.append("（AI 分析暂不可用）")
            # 展示原始列表
            all_items = []
            for cat in ["markets", "politics", "tech", "economics", "opinion"]:
                all_items.extend(data.get(cat, []))
            all_items.sort(key=lambda x: x["timestamp"], reverse=True)
            parts.append("")
            for it in all_items[:10]:
                cat_label = CATEGORY_LABELS.get(it["category"], it["category"])
                author = f" 👤 {it['author']}" if it.get("author") else ""
                parts.append(f"[{it['timestamp']}] {cat_label}: {it['text'][:100]}{author}")

        parts.append("")
        parts.append("━━━━━━━━━━━━━━━")
        parts.append(get_daily_tip())
        parts.append("")
        parts.append("（数据：Bloomberg RSS + Google News · 分析：AI）")

        return "\n".join(parts)

    def run(self) -> bool:
        slot_name, slot_label, hours, prefix = self._current_slot()

        # 防重发：每天每个 slot 只发一次
        slot_key = f"{prefix}_sent_{self.today}"
        if not self.force and self.state.has(slot_key):
            self.log(f"{self.now_str} {slot_label} 已发送过彭博日报")
            return True

        # 拉数据
        data = fetch_by_category(hours=hours)
        total = sum(len(v) for v in data.values())
        self.log(f"[{slot_label}] 拉取 {total} 条原始文章（市场{len(data['markets'])}"
                 f" 政策{len(data['politics'])} 科技{len(data['tech'])}"
                 f" 经济{len(data['economics'])} 观点{len(data['opinion'])}）")

        if total == 0:
            self.log("无数据，跳过推送")
            return True

        # AI 分析
        prompt = self._build_ai_prompt(data, slot_label, hours)
        analysis = ai_chat(prompt, temperature=0.5, max_tokens=3000)

        # 组装并发送
        report = self._format_report(data, analysis, slot_label, hours)
        if self.send(report):
            self.state.set(slot_key)
            self.state.save()
            self.log(f"✅ 已发送 {self.now_str}（{total} 条 → AI 精选，{slot_label}）")
            return True
        self.log("❌ 发送失败")
        return False
