"""意见领袖发言日报 -> 微信文章生成

格式与 bloomberg_wechat.py 一致，含合规风控过滤。
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from market_monitor.core.voice_sources import fetch_all
from market_monitor.core.ai import ai_chat
from market_monitor.core.teaching import get_daily_tip
from market_monitor.core.compliance import compliance_filter
from market_monitor.monitors.bloomberg_wechat import _extract_summary

PERSONS = ["trump", "musk", "jensen"]
PERSON_LABELS = {"trump": "川普", "musk": "马斯克", "jensen": "黄仁勋"}
MAX_PER_PERSON = 30


def _build_raw_section(items):
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


def _build_prompt(items):
    raw = _build_raw_section(items)
    today = datetime.now().strftime("%Y-%m-%d %A")
    return f"""你是一位资深美股分析师，专精"意见领袖发言 -> 市场影响"的联动分析。
下面是过去 24 小时 Trump / Musk / 黄仁勋 的公开发言汇总。

请完成两件事：

【第一步】重要性打分（仅内部思考，不要输出打分过程！）
对每条发言打 1-10 分（10 = 可能引发个股 5%+ 波动），只保留 ≥ 6 分的。
打分维度：
- 涉及具体政策/产品/公司 -> 加分
- 涉及关税/监管/并购/新品发布 -> 加分
- 纯社交/体育/祝福/转发无评论 -> 减分
- 模糊表态无实质内容 -> 减分

【第二步】直接输出日报

【格式要求--微信公众号文章，用 Markdown 标题渲染】
✅ 标题用 ## 分级，必须严格使用以下标题（AI不准自行修改）：
   ## 川普
   ## 马斯克
   ## 黄仁勋
✅ 每条发言固定格式，逐条列出（条目之间**不要空行**，紧凑排版）：
   [时间] 发言摘要（≤ 80 字）
   -> 影响：涉及xxx
   📊 关联标的：TSLA / NVDA
✅ 某人无 ≥ 6 分发言 -> 写"（无重要发言）"
✅ **最后一段必须是 ## 综合观察**--不能省略！
   - 100-200 字总结今日信号
✅ 中文，总字数 400-800 字
✅ 从 ## 川普 开始写，不要任何前置说明
✅ 不要用 # 一级标题（文章标题已自动生成）
✅ 不要用 --- 分割线、** 加粗、| 表格

发言数据：
{raw}

今天日期：{today}
"""


def generate_voice_article(items):
    prompt = _build_prompt(items)
    analysis = ai_chat(prompt, temperature=0.5, max_tokens=4000)
    if not analysis:
        return None

    # 合规过滤
    analysis = compliance_filter(analysis)
    if not analysis or len(analysis.strip()) < 50:
        return None

    # 综合观察提升为 # 一级标题
    analysis = analysis.replace("## 综合观察", "# 综合观察")

    title = "意见领袖发言日报"
    summary = _extract_summary(analysis)
    daily_tip = get_daily_tip()
    today = datetime.now().strftime("%Y-%m-%d")
    date_str = datetime.now().strftime("%Y年%m月%d日")

    md = f"""---
title: "{title}"
summary: "{summary}"
author: AI边用边想
date: {today}
---

# {title}

> 📅 {date_str} · 回溯 24 小时 · Trump / Musk / 黄仁勋

{analysis.strip()}

---

# 📚 每日锦囊

{daily_tip}

---

*本文由 AI 基于公开信息自动生成，仅供参考，不构成投资建议。*
"""
    return md


def main():
    hours = 24
    print(f"[voice_wechat] 拉取意见领袖数据（回溯 {hours}h）...", file=sys.stderr)
    items = fetch_all(PERSONS, hours=hours)
    # 截断
    by_person = {}
    for it in items:
        by_person.setdefault(it["person"], []).append(it)
    trimmed = []
    for p in PERSONS:
        trimmed.extend(by_person.get(p, [])[:MAX_PER_PERSON])
    trimmed.sort(key=lambda x: x["timestamp"], reverse=True)
    print(f"[voice_wechat] 共 {len(trimmed)} 条发言", file=sys.stderr)

    if not trimmed:
        print("[voice_wechat] 无数据，跳过", file=sys.stderr)
        return None

    print("[voice_wechat] AI 分析中...", file=sys.stderr)
    md = generate_voice_article(trimmed)
    if not md:
        print("[voice_wechat] AI 不可用或合规过滤后为空，跳过", file=sys.stderr)
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "post-to-wechat", today)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "voice-daily.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(out_path)
    return out_path


if __name__ == "__main__":
    main()