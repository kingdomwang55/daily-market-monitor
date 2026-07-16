"""全球宏观 & 财经日报（macro_monitor）

面向全球交易者的 24h 市场追踪，与 voice_monitor 分开推送。

4 大维度：
- 🏛️ 政策速递（Fed / SEC / Treasury）
- 📰 财经快讯（华尔街见闻 / 财联社 / 金十 / MktNews / FastBull）
- 📈 A 股&港股焦点（雪球热股 / 财联社深度）
- 🌐 全球宏观（Yahoo Finance / 36氪）

时段：12 时段同 voice（每 2h）
回溯窗口：自适应（盘中 2h、开收盘 6h、美盘 3h、静默 8h）
"""
import re
from datetime import datetime
from typing import List, Dict

from ..core.base import BaseMonitor
from ..core.news_sources import fetch_all_categories
from ..core.ai import ai_chat
from ..core.teaching import get_daily_tip


# 按 slot 定义回溯窗口（小时）
# slot = (hour // 2) * 2
SLOT_WINDOWS = {
    #  slot: (label, hours)
    0:  ("美盘中段",   3),
    2:  ("美盘中段",   3),
    4:  ("美盘尾盘",   3),
    6:  ("亚洲开盘前", 8),   # 静默兜底
    8:  ("A 股开盘",   6),   # 覆盖亚洲开盘前后
    10: ("A 股盘中",   2),
    12: ("A 股午后",   2),
    14: ("A 股收盘",   2),
    16: ("欧盘开启",   6),   # 覆盖 A 股收盘 → 欧盘
    18: ("欧盘盘中",   3),
    20: ("美股盘前",   3),
    22: ("美股开盘",   3),
}

# 每类最多送 AI 的条数（防止 token 爆掉）
MAX_PER_CATEGORY = {
    "policy":  10,
    "finance": 30,
    "astock":  20,
    "global":  15,
}

CATEGORY_LABELS = {
    "policy":  "🏛️ 政策速递",
    "finance": "📰 财经快讯",
    "astock":  "📈 A股&港股",
    "global":  "🌐 全球宏观",
}


class MacroMonitor(BaseMonitor):
    name = "macro"
    display_name = "全球宏观日报"

    def _current_window(self) -> tuple:
        """获取当前 slot 的窗口配置"""
        hour = self.now.hour
        slot = (hour // 2) * 2
        label, hours = SLOT_WINDOWS.get(slot, ("常规", 4))
        return slot, label, hours

    def _build_raw_section(self, data: Dict[str, List[Dict]]) -> str:
        """给 AI 看的原始新闻列表"""
        lines = []
        for cat, items in data.items():
            label = CATEGORY_LABELS.get(cat, cat)
            batch = items[:MAX_PER_CATEGORY.get(cat, 20)]
            if not batch:
                lines.append(f"\n== {label}（无新事件）==")
                continue
            lines.append(f"\n== {label}（{len(batch)} 条）==")
            for it in batch:
                lines.append(f"[{it['timestamp']}] ({it['source']}) {it['text'][:200]}")
        return "\n".join(lines)

    def _build_ai_prompt(self, data: Dict[str, List[Dict]],
                        slot_label: str, hours: int) -> str:
        raw = self._build_raw_section(data)
        today = datetime.now().strftime("%Y-%m-%d %A")

        return f"""你是一位资深全球宏观分析师，专精"新闻事件 → 市场影响"的联动分析。
下面是过去 {hours} 小时全球财经/政策/A股/宏观动态汇总。当前时段：{slot_label}。

请完成两件事：

【第一步】重要性打分（仅内部思考，不要输出打分过程！）
对每条新闻打 1-10 分，只保留满足门槛的：
- 政策速递（policy）：门槛 ≥ 7
- 财经快讯（finance）：门槛 ≥ 7
- A股焦点（astock）：门槛 ≥ 6
- 全球宏观（global）：门槛 ≥ 7

打分维度：
- 涉及 Fed 加息/降息/QT/关税/监管 → 加分
- 涉及大公司财报/并购/新品 → 加分
- 涉及地缘冲突/OPEC/原油/黄金 → 加分
- 涉及个股 ≥ 3% 波动或"龙头股" → 加分
- 通用宏观数据未大幅超预期 → 减分
- 无实质内容/软文/娱乐 → 减分

【第二步】直接输出日报

⚠⚠⚠ 最重要的输出规则（违反任意一条都是严重错误）：

【禁止使用任何 Markdown 符号】
❌ 不要使用 # 或 ## 或 ### 作为标题
❌ 不要使用 ** 或 __ 做加粗
❌ 不要使用 --- 或 === 做分割线
❌ 不要使用 | ... | 表格结构
❌ 不要使用 * 或 - 开头的列表
❌ 不要写"第一步：打分"这种内部思考过程
❌ 不要使用 ``` 代码块

【必须遵守的格式】
✅ 4 段结构，标题固定用【】包裹：
   【🏛️ 政策速递】
   【📰 财经快讯】
   【📈 A股&港股焦点】
   【🌐 全球宏观】
✅ 每条固定三行：
   [时间] 事件摘要（≤ 60 字）
   → 影响：涉及xxx
   📊 关联标的：TSLA / 上证 / 黄金
✅ 该段无 ≥ 门槛的新闻 → 写"（无重要事件）"
✅ 末尾【🎯 综合观察】一段总结当前市场信号（可含操作提示）
✅ 中文，总字数 500-800 字
✅ 直接从【🏛️ 政策速递】开始写，不要任何前置说明

【正确示例】
【🏛️ 政策速递】
[07-06 22:31] Fed 主席鲍威尔暗示 9 月不会降息
→ 影响：加息预期升温，压制风险资产
📊 关联标的：美股 / 黄金 / 美元指数

【📰 财经快讯】
（无重要事件）

【错误示例（千万不要）】
## 第一步：打分
**Fed**：
| 时间 | 事件 | 分数 |

新闻数据：
{raw}

今天日期：{today}
"""

    def _format_report(self, data: Dict[str, List[Dict]],
                      analysis: str, slot_label: str, hours: int) -> str:
        """组装最终推送文本"""
        parts = [
            f"🌍 全球宏观日报",
            f"📅 {self.now_str} · {slot_label}（回溯 {hours}h）",
            "",
        ]

        # 数据统计
        summary_parts = []
        for cat in ["policy", "finance", "astock", "global"]:
            n = len(data.get(cat, []))
            label = CATEGORY_LABELS[cat].split(" ", 1)[1]  # 去掉 emoji
            summary_parts.append(f"{label} {n}")
        parts.append(f"📊 事件数：{' · '.join(summary_parts)}")
        parts.append("")

        if analysis:
            parts.append("━━━━━━━━━━━━━━━")
            parts.append(analysis)
        else:
            parts.append("（AI 分析暂不可用）")

        parts.append("")
        parts.append("━━━━━━━━━━━━━━━")
        parts.append(get_daily_tip())
        parts.append("")
        parts.append("（数据：NewsNow / Fed / SEC / Yahoo · 分析：AI）")

        return "\n".join(parts)

    def run(self) -> bool:
        slot, slot_label, hours = self._current_window()

        # 防重发：每 2h 一个 slot
        slot_key = f"macro_sent_{self.today}_h{slot:02d}"
        if not self.force and self.state.has(slot_key):
            self.log(f"{self.now_str} 当前时段 (h{slot:02d} {slot_label}) 已发送过宏观日报")
            return True

        # 拉数据
        data = fetch_all_categories(hours=hours)
        total = sum(len(v) for v in data.values())
        self.log(f"[{slot_label}] 拉取 {total} 条原始事件（政策{len(data['policy'])}"
                 f" 财经{len(data['finance'])} A股{len(data['astock'])} 全球{len(data['global'])}）")

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
            self.log(f"✅ 已发送 {self.now_str}（{total} 条 → AI 精选，slot h{slot:02d} {slot_label}）")
            return True
        self.log("❌ 发送失败")
        return False
