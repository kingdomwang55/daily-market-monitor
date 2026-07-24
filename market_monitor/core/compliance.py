"""合规风控过滤模块（软过滤模式）

用于自媒体发布前的内容合规审查，过滤政治敏感内容。
软过滤策略：只删除极度敏感条目，其余改写中性表述。
"""
import re
import sys
from typing import Optional

from .ai import ai_chat


def _soft_sensitive_filter(text: str) -> str:
    """软过滤：只删除特别敏感的条目，其余改写中性表述"""
    
    # 极度敏感关键词（命中则整段移除）--只保留最核心的政治敏感
    ultra_sensitive = [
        # 核心政治人物
        '习近平', '李克强', '王毅', '秦刚',
        '总书记', '国家主席', '总理', '政治局',
        # 极度敏感地域
        '台湾', '台独', '台海', '香港', '新疆', '西藏',
        '南海', '钓鱼岛', '东海',
        # 极度敏感事件
        '六四', '8964', '天安门',
    ]
    
    # 需要中性化改写的词汇（不删除，只替换）
    # 战争/军事类 → 中性财经表述
    replace_map = {
        '战争': '地缘局势',
        '战争升级': '地缘局势升温',
        '全面战争': '全面地缘风险',
        '伊朗战争': '中东局势',
        '开辟新战线': '影响范围扩大',
        '攻击商船': '航运干扰',
        '红海攻击': '红海局势',
        '胡塞武装': '地方武装',
        '交火': '摩擦',
        '冲突': '局势',
        '军事': '相关',
        '军方': '相关方',
        '解放军': '相关方',
        '导弹': '相关设施',
        '军演': '相关活动',
        # 政治人物 → 弱化
        '特朗普': '美国政府',
        'Trump': 'US government',
        '拜登': '美国政府',
        'Biden': 'US government',
        # 其他敏感
        '共产党': '相关机构',
        '中共': '相关机构',
        '美国政府': '美方',
        '中国政府': '中方',
        '外交部': '相关部门',
        '国防部': '相关部门',
        '暴动': '动荡',
        '抗议': '民众活动',
        '示威': '聚集活动',
        '动乱': '社会变化',
        '暴乱': '社会事件',
        '核共享': '能源合作',
        '核协议': '相关协议',
        '第338条': '相关条款',
        'SVB审查': '金融监管',
        '罢免美联储': '人事调整',
        '无视威胁': '应对挑战',
        '硬闯': '通过',
        '经济疲软': '经济放缓',
        '情绪低落': '情绪谨慎',
        '融资受限': '融资规范',
        '闯红海': '通过红海航道',
    }
    
    lines = text.split('\n')
    result = []
    skip_block = False
    is_summary_section = False
    
    for line in lines:
        stripped = line.strip()
        
        # 标题行跳过所有敏感词处理
        if stripped.startswith('#'):
            # 追踪是否进入综合观察段落
            is_summary_section = '综合观察' in stripped
            result.append(line)
            continue
        
        # 综合观察段落：只做软替换，不删除
        if is_summary_section and stripped:
            for old, new in replace_map.items():
                line = line.replace(old, new)
            result.append(line)
            continue
        
        # 检测新条目开始
        is_new_item = stripped.startswith('[') and ']' in stripped[:30]
        
        if is_new_item:
            skip_block = any(term in stripped for term in ultra_sensitive)
        
        if skip_block:
            if is_new_item and not any(term in stripped for term in ultra_sensitive):
                skip_block = False
                # 替换敏感表述
                for old, new in replace_map.items():
                    line = line.replace(old, new)
                result.append(line)
            continue
        
        # 替换敏感表述
        for old, new in replace_map.items():
            line = line.replace(old, new)
        
        result.append(line)
    
    result = '\n'.join(result)
    
    # 压缩多余空行（最多保留1个空行作为段落分隔）
    import re
    result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
    
    return result


def _ai_compliance_review(text: str) -> Optional[str]:
    """AI 合规二审：平滑自然的表述优化"""
    prompt = f"""你是一位资深的中文财经编辑。

请对下面的财经文章进行合规润色，要求：

1. 移除任何涉及中国核心政治人物、敏感地域（台湾/新疆/西藏/南海等）的直接表述
2. 将战争、军事、冲突等词汇改写为中性财经表述（"地缘风险"、"局势变化"、"航运干扰"等）
3. 移除涉及外国政治人物的政治操作内容，只保留纯财经影响
4. 保持文章整体结构不变：## 标题 + 逐条列表格式
5. 保持每条的格式：[时间] 标题摘要 → 影响 → 📊 关联标的 → 👤 作者
6. 如果某段落所有条目都被移除，写"（无重要文章）"
7. 输出自然流畅的中文，不要留下明显删改痕迹
8. 保留 # 综合观察 段落，但润色其表述

只输出润色后的文章正文，不要输出其他说明。

【待处理文章】
{text}
"""
    result = ai_chat(prompt, temperature=0.3, max_tokens=4000)
    if not result:
        # AI 不可用时退回软过滤结果
        print('[compliance] AI 二审不可用，使用软过滤结果', file=sys.stderr)
        return text
    return result


def compliance_filter(text: str) -> str:
    """合规风控过滤（软过滤模式）

    第一层：软过滤 - 只删除极度敏感条目，其余改写中性表述
    第二层：AI 合规二审 - 平滑自然的润色优化

    Args:
        text: AI 生成的文章内容（Markdown）

    Returns:
        过滤后的合规文本。如果过滤后内容过短，返回空字符串。
    """
    if not text:
        return text

    # 第一层：软过滤（只删核心敏感）
    filtered = _soft_sensitive_filter(text)

    # 第二层：AI 合规二审
    filtered = _ai_compliance_review(filtered)

    # 质量检查
    plain = re.sub(r'[#*\-\[\]\n\s>📊👤📅━]', '', filtered)
    if len(plain) < 100:
        print(f'[compliance] 过滤后内容过短（{len(plain)}字），放弃发布', file=sys.stderr)
        return ''

    return filtered
