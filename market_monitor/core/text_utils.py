"""文本工具：markdown → 飞书 text 消息友好的纯文本"""
import re


def strip_markdown(text: str) -> str:
    """兜销 AI/教学解读里的 markdown 符号，转为适合飞书 text 消息的纯文本。

    处理规则（保守）：
    - 删除 markdown 表格的分隔行 |---|---|
    - 删除 --- / === 分割线
    - 删除 ``` 代码块围栏
    - 行首 # / ## / ### 标题符号去掉
    - 行首列表符号 - * + 去掉
    - 行内 **加粗**、__加粗__ → 加粗
    - 行内 *斜体*、_斜体_ → 斜体（对单星号做严格匹配，避免误伤 *xxx* 中的 * ）
    - 行内 `代码` → 代码
    - 表格行 | a | b | → a  b（用双空格分隔）
    - 压缩 3+ 空行为 2 行

    保留：
    - emoji、【】、→、📊、• 等有效符号
    - MA5/MA10 等技术指标里的 * 不会被误伤（因为不成对）
    """
    if not text:
        return text

    lines = text.split("\n")
    out = []
    for line in lines:
        stripped = line.strip()

        # 跳过表格分隔行 |---|---|
        if re.match(r"^\|[\s\-:|]+\|?\s*$", stripped):
            continue
        # 跳过 --- === 分割线（3 个及以上）
        if re.match(r"^[-=]{3,}\s*$", stripped):
            continue
        # 跳过 ``` 代码块围栏（保留代码块内容）
        if re.match(r"^```", stripped):
            continue

        # 行首 # / ## / ### 标题
        line = re.sub(r"^#{1,6}\s+", "", line)
        # 行首列表符号 * / +
        line = re.sub(r"^(\s*)[*+]\s+", r"\1", line)
        # 行首 - 列表（区分于内联的 → 等）
        line = re.sub(r"^(\s*)-\s+(?!>)", r"\1", line)

        # 表格行：| a | b | → a  b
        if line.count("|") >= 2 and line.strip().startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            line = "  ".join(cells)

        # 行内 **加粗** → 加粗
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        # 行内 __加粗__ → 加粗
        line = re.sub(r"__(.+?)__", r"\1", line)
        # 行内 *斜体* → 斜体（严格：前后都不能是 *，避免误吃 **）
        line = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", line)
        # 行内 `代码` → 代码
        line = re.sub(r"`([^`]+)`", r"\1", line)

        out.append(line)

    # 压缩连续 3+ 空行为 2 行
    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
