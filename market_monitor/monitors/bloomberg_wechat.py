"""Bloomberg 发文日报 → 微信文章生成

输出精美排版的微信文章，包含：
- 带 theme 样式的分级标题
- 逐条详细的新间列表
- 综合观察 + 每日锦囊
- AI 不可用时跳过
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from market_monitor.core.bloomberg_sources import fetch_by_category, CATEGORY_LABELS
from market_monitor.core.ai import ai_chat
from market_monitor.core.teaching import get_daily_tip
from market_monitor.core.compliance import compliance_filter
from market_monitor.core.cover_utils import get_cover_url

MAX_PER_CATEGORY = {
    "markets":   15,
    "politics":  10,
    "tech":      10,
    "economics": 10,
    "opinion":   10,
}

CATEGORY_KEYS = ["markets", "politics", "tech", "economics", "opinion"]


def _build_raw_section(data: dict) -> str:
    """给 AI 看的原始文章列表"""
    lines = []
    for cat in CATEGORY_KEYS:
        label = CATEGORY_LABELS.get(cat, cat)
        items = data.get(cat, [])
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


def build_wechat_prompt(data: dict) -> str:
    """构建微信版 AI 分析 prompt（允许 Markdown 标题，以匹配 theme 渲染）"""
    raw = _build_raw_section(data)
    today = datetime.now().strftime("%Y-%m-%d %A")

    return f"""你是一位资深全球宏观/美股分析师，专精"彭博社发文 → 市场影响"的联动分析。

下面是过去 24 小时彭博社 Bloomberg 的报道/观点汇总。

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

【格式要求——这是微信公众号文章，用 Markdown 标题渲染】
✅ 标题用 ## 分级（会被渲染成带样式的标题区块）：
   ## 市场
   ## 政策/地缘
   ## 科技
   ## 经济/央行
   ## 观点/分析
✅ 每条固定格式，逐条列出，不能合并成段落：
   [时间] 文章标题摘要（≤ 60 字，必须翻译成中文！不要输出英文原标题）
   → 影响：涉及xxx
   📊 关联标的：SPY / 黄金 / 原油 / TSLA / 上证
   👤 作者：xxx（如果原始数据有作者名则写，没有则整行省略，不要写"不详"或"未署名"）
✅ 该段无 ≥ 7 分的文章 → 写"（无重要文章）"
✅ 额外增加一段 ## 知情人爆料（放在观点段之后，中国相关段之前）：
   - 从所有文章中筛选包含"知情人/爆料/独家来源"特征的文章，门槛降低到 ≥ 6 分
   - 每条同样格式：[时间]标题摘要 → 影响 → 📊 关联标的 → 👤 作者
   - 如果完全没有，写"（无重要爆料）"
✅ 额外增加一段 ## 中国相关（放在爆料段之后，综合观察段之前）：
   - 从所有文章中筛选与中国/A股/港股/中概股相关的文章，门槛降低到 ≥ 6 分
   - 每条同样格式
   - 如果完全没有，写"（无重要中国相关文章）"
✅ **最后一段必须是 ## 综合观察**——非常重要，不能省略！
   - 一段 100-200 字的分析总结，含对中国市场影响判断
   - 若有知情人爆料，需评价"爆料可信度/市场冲击"
✅ 中文，总字数 1000-1500 字
✅ 从 ## 市场 开始写，不要任何前置说明
✅ 不要用 # 一级标题（文章标题已自动生成）
✅ 不要用 --- 分割线
✅ 不要用 ** 加粗
✅ 不要用 | 表格

彭博文章数据：
{raw}

今天日期：{today}
"""


def generate_wechat_article(data: dict) -> str:
    """生成微信文章的 Markdown 内容，包含合规风控过滤"""
    prompt = build_wechat_prompt(data)
    analysis = ai_chat(prompt, temperature=0.5, max_tokens=6000)
    if not analysis:
        return None

    # 合规风控过滤（仅对微信草稿箱版本）
    analysis = compliance_filter(analysis)
    if not analysis:
        print("[bloomberg_wechat] 合规过滤后内容为空，跳过", file=sys.stderr)
        return None

    # 从 AI 输出提取标题
    title = "彭博社发文日报"
    for line in analysis.strip().split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("##"):
            title = line[2:].strip()
            break

    # 确保综合观察存在（用 # 一级标题，居中显示）
    if "# 综合观察" not in analysis:
        analysis += "\n\n" + _generate_fallback_observation(data)

    # 确保中国相关存在（但如果 AI 没输出且被合规过滤掉了，不要强行补回）
    # if "## 中国相关" not in analysis:
    #     china = _generate_fallback_china(data)
    #     if china:
    #         analysis += "\n\n" + china

    # 确保知情人爆料存在（但如果 AI 没输出且被合规过滤掉了，不要强行补回）
    # if "## 知情人爆料" not in analysis:
    #     insider = _generate_fallback_insider(data)
    #     if insider:
    #         analysis += "\n\n" + insider

    # 排版处理：综合观察 用 # 一级标题（居中），其他分类用 ## 二级标题
    # 把 AI 输出的 ## 综合观察 提升为 # 综合观察（居中）
    analysis = analysis.replace("## 综合观察", "# 综合观察")

    # 摘要
    summary = _extract_summary(analysis)

    # 每日锦囊
    daily_tip = get_daily_tip()

    # 组装 Markdown——精美排版
    today = datetime.now().strftime("%Y-%m-%d")
    date_str = datetime.now().strftime("%Y年%m月%d日")
    cover_url = get_cover_url("bloomberg", "16x9")
md = f"""---
title: "{title}"
summary: "{summary}"
author: AI边用边想
date: {today}
cover: "{cover_url}"
---

# {title}

![cover]({cover_url})

> 📅 {date_str} · 回溯 24 小时 · 彭博社全球报道精选

{analysis.strip()}

---

# 📚 每日锦囊

{daily_tip}

---

*本文由 AI 基于彭博社最新报道整理，仅供参考，不构成投资建议。*
"""
    return md



def _compliance_filter(text: str) -> str:
    """自媒体推送合规风控过滤：移除政治敏感内容，仅保留纯市场/财经分析
    
    过滤策略：按文章条目（以 [时间] 开头的块）为单位过滤，
    包含敏感词的整条删除，同时删除空标题段。
    """
    # 敏感关键词（出现即移除整条）
    sensitive_terms = [
        '特朗普', 'Trump', 'Biden', '拜登',
        '共产党', '总书记', '国家主席', '总理', '政治局', '中央军委',
        '习近平', '李克强', '王毅', '秦刚',
        '战争', '军队', '军事', '军方', '解放军', '导弹', '军演',
        '台独', '台湾', '台海', '海峡',
        '香港', '新疆', '西藏', '六四',
        '南海', '钓鱼岛', '东海',
        '美国政府', '中国政府', '外交部', '国防部',
        '暴动', '抗议', '示威', '动乱', '暴乱',
        '伊朗战争', 'Iran war', '战争预算',
        '核共享', '核协议', '核技术共享',
        'SVB审查', '罢免美联储', '驱逐美联储',
        '胡塞', 'Houthi', '红海攻击',
        '关税威胁', '第338条',
    ]
    
    lines = text.split('\n')
    filtered = []
    skip_block = False
    
    for line in lines:
        # 检测新条目开始（[时间] 格式）
        is_new_item = line.strip().startswith('[') and ']' in line[:30]
        
        if is_new_item:
            # 检查这条是否敏感
            block_text = line
            skip_block = any(term in block_text for term in sensitive_terms)
        
        # 如果在跳过模式中，遇到下一条或空行就停止跳过
        if skip_block:
            if is_new_item and not any(term in line for term in sensitive_terms):
                skip_block = False
                filtered.append(line)
            elif line.strip() == '':
                skip_block = False
                filtered.append(line)
            # 否则跳过这行
        else:
            # 非条目行也检查敏感词，但跳过标题行（## 开头）
            stripped = line.strip()
            if stripped.startswith('#'):
                # 标题行直接保留（## Trump 等分类标题不过滤）
                filtered.append(line)
            elif any(term in line for term in sensitive_terms):
                line_safe = line
                for term in sensitive_terms:
                    if term in line_safe:
                        line_safe = line_safe.replace(term, 'XX')
                filtered.append(line_safe)
            else:
                filtered.append(line)
    
    # 清理空标题段（标题下没有任何内容的 ## 段）
    result = '\n'.join(filtered)
    
    return result

def _extract_summary(text: str, max_len: int = 120) -> str:
    import re
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if len(para) > 20:
            if len(para) > max_len:
                return para[:max_len].rstrip("。，,.;:") + "…"
            return para
    return "彭博社今日重要报道汇总"


def _generate_fallback_observation(data: dict) -> str:
    """AI 未输出综合观察时的程序化降级"""
    lines = ["# 综合观察"]

    themes = []
    for cat in CATEGORY_KEYS:
        items = data.get(cat, [])
        if items:
            label = CATEGORY_LABELS.get(cat, cat).split(" ", 1)[-1]
            themes.append(f"{label} {len(items)} 条")

    lines.append(f"今日彭博社报道覆盖了{'、'.join(themes)}。")

    china_kw = ['china', 'chinese', 'hong kong', 'shanghai', '中国', '港股', 'a股', '人民币', '上证', '恒生', '房地产', '半导体']
    china_items = [it for it in sum(data.values(), [])
                   if any(kw in (it['text'] + it.get('summary', '')).lower() for kw in china_kw)]
    if china_items:
        lines.append("其中中国相关报道较为密集，涉及半导体公司赴港上市、AI模型追赶、房地产融资收紧等维度。整体来看，彭博对中国市场的报道偏向中性，科技自主叙事提供正向支撑，但房地产和南海地缘风险构成压制。")
    else:
        lines.append("中国相关报道较少，市场关注焦点集中在伊朗战争、美联储独立性和贸易战升级等全球性议题上。")

    lines.append("地缘政治风险和政策不确定性仍是当前全球市场的主旋律，投资者需关注油价走势和央行政策转向信号。")

    return "\n".join(lines)


def _generate_fallback_china(data: dict) -> str:
    china_kw = ['china', 'chinese', 'hong kong', 'shanghai', 'shenzhen', 'beijing',
                '中概', '港股', 'a股', '人民币', '上证', '恒生', '中国', '半导体', '房地产']
    china_items = []
    for it in sum(data.values(), []):
        text = (it['text'] + ' ' + it.get('summary', '')).lower()
        if any(kw in text for kw in china_kw):
            china_items.append(it)
    if not china_items:
        return ""

    lines = ["## 中国相关"]
    for it in china_items[:8]:
        author = f"\n👤 {it['author']}" if it.get('author') else ""
        lines.append(f"[{it['timestamp']}] {it['text'][:80]}")
        lines.append(f"→ 涉及：{it['category']}")
        lines.append(f"📊 关联标的：中国资产{author}")
    return "\n".join(lines)


def _generate_fallback_insider(data: dict) -> str:
    insider_kw = ['people familiar', '知情人士', 'sources say', 'disclosed', 'leak',
                  'confidential', 'secret', 'internal', 'memo', 'leaked', '私下',
                  '提前', '即将宣布', '独家', '独家报道', 'reveals']
    insider_items = []
    for it in sum(data.values(), []):
        text = (it['text'] + ' ' + it.get('summary', '')).lower()
        if any(kw in text for kw in insider_kw):
            insider_items.append(it)
    if not insider_items:
        return ""

    lines = ["## 知情人爆料"]
    for it in insider_items[:5]:
        author = f"\n👤 {it['author']}" if it.get('author') else ""
        lines.append(f"[{it['timestamp']}] {it['text'][:80]}")
        lines.append(f"→ 涉及：{it['category']}")
        lines.append(f"📊 关联标的：待定{author}")
    return "\n".join(lines)


def main():
    hours = 24
    print(f"[bloomberg_wechat] 拉取彭博社数据（回溯 {hours}h）...", file=sys.stderr)
    data = fetch_by_category(hours=hours)
    total = sum(len(v) for v in data.values())
    print(f"[bloomberg_wechat] 共 {total} 条文章", file=sys.stderr)
    if total == 0:
        print("[bloomberg_wechat] 无数据，跳过", file=sys.stderr)
        return None
    print("[bloomberg_wechat] AI 分析中...", file=sys.stderr)
    md = generate_wechat_article(data)
    if not md:
        print("[bloomberg_wechat] AI 不可用，跳过本次推送", file=sys.stderr)
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "post-to-wechat", today)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "bloomberg-daily.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(out_path)
    return out_path


if __name__ == "__main__":
    main()