"""意见领袖发言监控（Phase 1: Trump / Musk / Jensen）

每日 07:30 推送，覆盖过去 24 小时重要发言。
AI 打分 ≥ 6 分才推，避免噪声。
"""
import json
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

## 第一步：重要性打分
对每条发言打 1-10 分（10 = 可能引发个股 5%+ 波动），只保留 ≥ 6 分的。
打分维度：
- 涉及具体政策/产品/公司 → 加分
- 涉及关税/监管/并购/新品发布 → 加分
- 纯社交/体育/祝福/转发无评论 → 减分
- 模糊表态无实质内容 → 减分

## 第二步：输出日报

格式要求：
1. 用【】标题分段，按人物分组
2. 每条保留发言格式：
   [时间] 发言摘要（≤80字）
   → 影响：涉及xxx
   📊 关联标的：TSLA / NVDA / 等
3. 如果某人在 24h 内无 ≥ 6 分发言，写"（无重要发言）"
4. 末尾加【综合观察】一段，总结今日意见领袖整体信号
5. 中文，总字数 400-600 字
6. 不要用 markdown 的 # 或 * 或 --- 符号
7. 每条发言摘要严格 ≤ 80 字

发言数据：
{raw}

今天日期：{today}
"""

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
        # 防重发
        daily_key = f"voice_sent_{self.today}"
        if not self.force and self.state.has(daily_key):
            self.log(f"{self.now_str} 今天已发送过意见领袖日报")
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
                self.state.set(daily_key)
                self.state.save()
                return True
            return False

        # AI 分析 + 打分
        prompt = self._build_ai_prompt(items)
        analysis = ai_chat(prompt, temperature=0.5, max_tokens=1200)

        report = self._format_report(items, analysis)

        if self.send(report):
            self.state.set(daily_key)
            self.state.save()
            self.log(f"✅ 已发送 {self.now_str}（{len(items)} 条原始 → AI 筛选）")
            return True
        self.log("❌ 发送失败")
        return False
