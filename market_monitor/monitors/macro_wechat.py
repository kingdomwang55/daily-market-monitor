"""全球宏观日报 → 微信公众号文章（同 bloomberg_wechat 格式）

生成同 bloomberg_wechat 风格的 Markdown：
- 带 theme 样式的分级标题
- 逐条详细的新闻列表
- 综合观察 + 每日锦囊
- AI 不可用时跳过

⚠️ 重要：此版本是自媒体发布专用（合规风控已启用），
⚠️ 定时推送的飞书版本用 macro_monitor.py（原汁原味无过滤）
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from market_monitor.core.news_sources import fetch_all_categories
from market_monitor.core.ai import ai_chat
from market_monitor.core.teaching import get_daily_tip
from market_monitor.core.compliance import compliance_filter
from market_monitor.core.cover_utils import get_cover_url

# 每类最多送 AI 的条数
MAX_PER_CATEGORY = {
    "policy":  10,
    "finance": 25,
    "astock":  15,
    "global":  15,
}

CATEGORY_LABELS = {
    "policy":  "🏛️ 政策速递",
    "finance": "📰 财经快讯",
    "astock":  "📈 A股&港股",
    "global":  "🌐 全球宏观",
}


def _build_raw_section(data: dict) -> str:
    """给 AI 看的原始新闻列表"""
    lines = []
    for cat, label in CATEGORY_LABELS.items():
        items = data.get(cat, [])
        batch = items[:MAX_PER_CATEGORY.get(cat, 20)]
        if not batch:
            lines.append(f"\n== {label}（无新事件）==")
            continue
        lines.append(f"\n== {label}（{len(batch)} 条）==")
        for it in batch:
            lines.append(f"[{it['timestamp']}] ({it['source']}) {it['text'][:200]}")
    return "\n".join(lines)


def build_wechat_prompt(data: dict, hours: int) -> str:
    """构建微信版 AI 分析 prompt（允许 Markdown 标题，以匹配 theme 渲染）"""
    raw = _build_raw_section(data)
    today = datetime.now().strftime("%Y-%m-%d %A")

    return f"""你是一位资深全球宏观分析师，专精"新闻事件 → 市场影响"的联动分析。

下面是过去 {hours} 小时全球财经/政策/A股/宏观动态汇总。

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

【格式要求——这是微信公众号文章，用 Markdown 标题渲染】
✅ 标题用 ## 分级（会被渲染成带样式的标题区块）：
   ## 🏛️ 政策速递
   ## 📰 财经快讯
   ## 📈 A股&港股
   ## 🌐 全球宏观
✅ 每条固定三行：
   [时间] 事件摘要（≤ 60 字）
   → 影响：涉及xxx
   📊 关联标的：TSLA / 上证 / 黄金
✅ 不要输出 👤 作者行（全球宏观日报不需要作者信息）
✅ 该段无满足门槛的新闻 → 写"（无重要事件）"
✅ 最后一段必须是 ## 🎯 综合观察（非常重要，不能省略！）
✅ 中文，总字数 700-1200 字
✅ 从 ## 🏛️ 政策速递 开始写，不要任何前置说明
✅ 不要用 # 一级标题（文章标题已自动生成）
✅ 不要用 --- 分割线
✅ 不要用 ** 加粗
✅ 不要用 | 表格

新闻数据：
{raw}

今天日期：{today}
"""


def generate_wechat_article(data: dict, hours: int) -> str:
    """生成微信文章的 Markdown 内容"""
    prompt = build_wechat_prompt(data, hours)
    analysis = ai_chat(prompt, temperature=0.5, max_tokens=4500)
    if not analysis:
        return None

    # 合规风控过滤（自媒体发布专用）
    analysis = compliance_filter(analysis)
    if not analysis:
        print("[macro_wechat] 合规过滤后内容为空，跳过", file=sys.stderr)
        return None

    # 确保综合观察存在
    if "## 🎯 综合观察" not in analysis:
        analysis += "\n\n## 🎯 综合观察\n当前全球市场整体平稳，关注后续政策与地缘变化。"

    # 每日锦囊
    daily_tip = get_daily_tip()

    # 组装 Markdown
    today = datetime.now().strftime("%Y-%m-%d")
    date_str = datetime.now().strftime("%Y年%m月%d日")
    cover_url = get_cover_url("macro", "16x9")
md = f"""---
title: "全球宏观日报"
summary: "过去 {hours} 小时全球财经与市场动态精选"
author: AI边用边想
date: {today}
cover: "{cover_url}"
---

# 全球宏观日报

![cover]({cover_url})

> 📅 {date_str} · 回溯 {hours} 小时 · 全球财经精选

{analysis.strip()}

---

# 📚 每日锦囊

{daily_tip}

---

*本文由 AI 基于全球新闻自动整理，仅供参考，不构成投资建议。*
"""
    return md


def main():
    hours = 24
    print(f"[macro_wechat] 拉取全球宏观数据（回溯 {hours}h）...", file=sys.stderr)
    data = fetch_all_categories(hours=hours)
    total = sum(len(v) for v in data.values())
    print(f"[macro_wechat] 共 {total} 条新闻事件", file=sys.stderr)
    if total == 0:
        print("[macro_wechat] 无数据，跳过", file=sys.stderr)
        return None
    print("[macro_wechat] AI 分析中...", file=sys.stderr)
    md = generate_wechat_article(data, hours)
    if not md:
        print("[macro_wechat] AI 不可用，跳过本次推送", file=sys.stderr)
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "post-to-wechat", today)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "macro-daily.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(out_path)
    return out_path


if __name__ == "__main__":
    main()
