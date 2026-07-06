"""意见领袖发言监控（Phase 1: Trump / Musk / Jensen）

每日 07:30 推送，覆盖过去 24 小时重要发言。
AI 打分 ≥ 6 分才推，避免噪声。
"""
import json
import re
import sys
from datetime import datetime
from typing import List, Dict

from ..core.base import BaseMonitor
from ..core.voice_sources import fetch_all
from ..core.ai import ai_chat
from ..core.teaching import get_daily_tip


# Phase 1 监控对象
PERSONS = ["trump", "musk", "jensen"]

PERSON_LABELS = {
    "trump": "Trump",
    "musk": "Musk",
    "jensen": "黄仁勋",
}

# 每人最多保留条数（防止 Trump 一天发 50 条刷屏）
MAX_PER_PERSON = 30


class VoiceMonitor(BaseMonitor):
    name = "voice"
    display_name = "意见领袖发言"

    def _gather_all(self) -> List[Dict]:
        """拉取过去 24h 所有发言"""
        items = fetch_all(PERSONS, hours=24)
        # 每人截断
        by_person = {}
        for it in items:
            by_person.setdefault(it["person"], []).append(it)
        trimmed = []
        for p in PERSONS:
            batch = by_person.get(p, [])[:MAX_PER_PERSON]
            trimmed.extend(batch)
        # 重新按时间倒序
        trimmed.sort(key=lambda x: x["timestamp"], reverse=True)
        return trimmed

    def _build_raw_section(self, items: List[Dict]) -> str:
        """生成原始发言列表（给 AI 看的）"""
        lines = []
        for p in PERSONS:
            batch = [it for it in items if it["person"] == p]
            label = PERSON_LABELS.get(p, p)
            if not batch:
                lines.append(f"\n== {label}（无发言）==")
                continue
            lines.append(f"\n== {label}（{len(batch)} 条）==")
            for it in batch:
                lines.append(f"[{it['timestamp']}] {it['text'][:300]}")
        return "\n".join(lines)

    def _build_ai_prompt(self, items: List[Dict]) -> str:
        raw = self._build_raw_section(items)
        today = datetime.now().strftime("%Y-%m-%d %A")

        return f"""你是一位资深美股分析师，专精"意见领袖发言 → 市场影响"的联动分析。
下面是过去 24 小时 Trump / Musk / 黄仁勋 的公开发言汇总。

请完成两件事：

【第一步】重要性打分（仅内部思考，不要输出打分过程！）
对每条发言打 1-10 分（10 = 可能引发个股 5%+ 波动），只保留 ≥ 6 分的。
打分维度：
- 涉及具体政策/产品/公司 → 加分
- 涉及关税/监管/并购/新品发布 → 加分
- 纯社交/体育/祝福/转发无评论 → 减分
- 模糊表态无实质内容 → 减分

【第二步】直接输出日报

⚠⚠⚠ 最重要的输出规则（违反任意一条都是严重错误）：

【禁止使用任何 Markdown 符号】
❌ 不要使用 # 或 ## 或 ### 作为标题（使用【】代替）
❌ 不要使用 ** 或 __ 做加粗
❌ 不要使用 --- 或 === 做分割线
❌ 不要使用 | ... | 表格结构
❌ 不要使用 * 或 - 开头的列表（直接写句子即可）
❌ 不要写 "第一步：重要性打分" 这种内部思考过程
❌ 不要使用 ``` 代码块

【必须遵守的格式】
✅ 标题用【】包裹，如【Trump】、【Musk】、【黄仁勋】、【综合观察】
✅ 每条发言固定三行：
   [时间] 发言摘要（≤ 80 字）
   → 影响：涉及xxx
   📊 关联标的：TSLA / NVDA
✅ 某人 24h 内无 ≥ 6 分发言 → 写“（无重要发言）”
✅ 末尾【综合观察】一段总结今日信号
✅ 中文，总字数 400-600 字
✅ 直接从【Trump】开始写，不要任何前置说明

【正确示例】
【Musk】
[2026-07-05 22:31] 马斯克称Optimus机器人初期生产将“极其缓慢”。
→ 影响：涉及特斯拉机器人量产节奏，低于预期
📊 关联标的：TSLA

【错误示例（千万不要）】
## 第一步：打分
**Musk**：
| 人物 | 时间 | 打分 |

发言数据：
{raw}

今天日期：{today}
"""

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """兼销 AI 返回里的 markdown 符号，转为适合飞书 text 消息的纯文本"""
        if not text:
            return text
        lines = text.split("\n")
        out = []
        for line in lines:
            stripped = line.strip()
            # 去掉表格分隔行 |---|---|
            if re.match(r"^\|[\s\-:|]+\|?\s*$", stripped):
                continue
            # 去掉 --- === 分割线（保留代码里的 ─ 字符）
            if re.match(r"^[-=]{3,}\s*$", stripped):
                continue
            # 去掉 markdown 代码块围栏
            if re.match(r"^```", stripped):
                continue
            # 去掉行首 # 标题标记
            line = re.sub(r"^#{1,6}\s+", "", line)
            # 行首列表标记 * / - / + （但不影响→ 等行）
            line = re.sub(r"^(\s*)[*+]\s+", r"\1", line)
            # 行首 - 列表（区分于→符号）
            line = re.sub(r"^(\s*)-\s+(?![>])", r"\1", line)
            # 表格行：| a | b | → a  b
            if line.count("|") >= 2 and line.strip().startswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                line = "  ".join(cells)
            # 内联加粗 **xxx** → xxx
            line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            # 内联斜体 *xxx* → xxx（避免影响★等）
            line = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", line)
            # __xxx__ → xxx
            line = re.sub(r"__(.+?)__", r"\1", line)
            # 行内代码 `xxx` → xxx
            line = re.sub(r"`([^`]+)`", r"\1", line)
            out.append(line)
        # 压缩连续空行
        result = "\n".join(out)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()

    def _format_report(self, items: List[Dict], analysis: str) -> str:
        """组装最终推送文本"""
        parts = [
            f"🗣️ 意见领袖发言日报",
            f"📅 {self.now_str}",
            "",
        ]

        # 统计
        counts = {}
        for it in items:
            counts[it["person"]] = counts.get(it["person"], 0) + 1
        summary_parts = []
        for p in PERSONS:
            label = PERSON_LABELS.get(p, p)
            n = counts.get(p, 0)
            summary_parts.append(f"{label} {n}条")
        parts.append(f"📊 过去 24h：{' · '.join(summary_parts)}")
        parts.append("")

        if analysis:
            parts.append("━━━━━━━━━━━━━━━")
            parts.append(f"🤖 AI 分析（仅展示重要性 ≥ 6 分）")
            parts.append("")
            parts.append(analysis)
        else:
            # AI 不可用时，展示原始列表
            parts.append("（AI 分析暂不可用，展示原始发言）")
            parts.append("")
            for it in items[:10]:
                label = PERSON_LABELS.get(it["person"], it["person"])
                parts.append(f"[{it['timestamp']}] {label}: {it['text'][:100]}")

        parts.append("")
        parts.append("━━━━━━━━━━━━━━━")
        parts.append(get_daily_tip())
        parts.append("")
        parts.append("（数据：Truth Social / Nitter / Google News · 分析：AI）")

        return "\n".join(parts)

    def run(self) -> bool:
        # 防重发：每 2 小时一个独立 slot（0/2/4/.../22），同 slot 内重跑才拦
        hour = datetime.now().hour
        slot = (hour // 2) * 2
        slot_key = f"voice_sent_{self.today}_h{slot:02d}"
        if not self.force and self.state.has(slot_key):
            self.log(f"{self.now_str} 当前时段 (h{slot:02d}) 已发送过意见领袖日报")
            return True

        items = self._gather_all()
        if not items:
            self.log("未获取到任何发言数据")
            # 仍然推送一条"今日无重要发言"
            report = (
                f"🗣️ 意见领袖发言日报\n📅 {self.now_str}\n\n"
                f"过去 24h 未抓取到 Trump / Musk / 黄仁勋 的发言数据。\n"
                f"可能是数据源暂时不可用。\n\n（数据：Truth Social / Nitter / Google News）"
            )
            if self.send(report):
                self.state.set(slot_key)
                self.state.save()
                return True
            return False

        # AI 分析 + 打分
        prompt = self._build_ai_prompt(items)
        analysis = ai_chat(prompt, temperature=0.5, max_tokens=1200)
        analysis = self._strip_markdown(analysis) if analysis else analysis

        report = self._format_report(items, analysis)

        if self.send(report):
            self.state.set(slot_key)
            self.state.save()
            self.log(f"✅ 已发送 {self.now_str}（{len(items)} 条原始 → AI 筛选，slot h{slot:02d}）")
            return True
        self.log("❌ 发送失败")
        return False
