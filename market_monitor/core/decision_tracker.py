"""决策闭环追踪

从 push_logger 的推送记录中提取可校验的"决策/预测"，
然后在下一个时间窗口自动比对实际结果，生成复盘报告。

核心流程：
  1. extract  — AI 从推送原文中抽取可校验命题
  2. verify   — AI + 市场实际数据 比对 → hit / miss / partial
  3. review   — 汇总成周报复盘

存储：logs/decisions/YYYY-MM-DD.jsonl
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

from . import push_logger
from . import data_source as ds
from .ai import ai_chat

_DECISIONS_ROOT = Path(__file__).resolve().parent.parent.parent / "logs" / "decisions"


# ── 提取 ────────────────────────────────────────────────

_EXTRACT_PROMPT = """你是一个金融决策追踪系统。从以下推送消息中提取所有**可检验的预测/判断/操作建议**。

## 什么是"可检验命题"？
必须同时满足：
1. **有方向**：看多/看空/企稳/承压/加仓/止损/关注（中性）
2. **有对象**：指数/板块/个股/资金流/宏观指标
3. **有时限**：日内/次日/本周/短期

## 反例（不提取）
- "市场波动加剧"（无方向）
- "长期看好AI"（时限太长无法检验）
- "建议保持谨慎"（太模糊）

## 输出格式
严格返回 JSON 数组，每个元素：
{
  "claim": "简洁命题（15字内）",
  "direction": "bullish|bearish|neutral",
  "subject": "对象（指数名/板块名/个股/指标）",
  "timeframe": "intraday|next-day|this-week|short-term",
  "source_type": "推送类型（morning/evening/hk_market等）",
  "confidence": "explicit|implied"
}
- explicit: 原文明确说的（"恒指高开"）
- implied: 从上下文推断的（"关注科技板块"→隐含看多）

只返回 JSON 数组，不要其他文字。没有可检验命题时返回 []。"""


def _day_path(date_str: str) -> Path:
    return _DECISIONS_ROOT / f"{date_str}.jsonl"


def extract_decisions(date_str: str) -> List[Dict]:
    """从某天的所有推送中提取可检验命题。

    Returns:
        list[dict] 决策记录（已持久化到 logs/decisions/）
    """
    records = push_logger.read_day(date_str)
    if not records:
        return []

    # 合并同一天所有推送
    combined = []
    for r in records:
        t = r.get("type", "unknown")
        msg = r.get("message", "")
        if not msg.strip():
            continue
        combined.append(f"[{t}] {msg[:2000]}")  # 截断防止 token 爆炸

    if not combined:
        return []

    full_text = "\n\n---\n\n".join(combined)
    prompt = f"{_EXTRACT_PROMPT}\n\n## 推送原文\n\n{full_text[:8000]}"

    result = ai_chat(prompt, temperature=0.2, max_tokens=2000, timeout=90)
    if not result:
        print("[decision_tracker] AI 提取失败", file=sys.stderr)
        return []

    # 解析 JSON
    try:
        # 去掉可能的 markdown 代码块包裹
        text = result.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
        decisions = json.loads(text)
    except json.JSONDecodeError:
        print(f"[decision_tracker] JSON 解析失败: {result[:200]}", file=sys.stderr)
        return []

    if not isinstance(decisions, list):
        return []

    # 补充元信息并去重（按 claim 去重，保留首次出现）
    enriched = []
    seen_claims = set()
    _DECISIONS_ROOT.mkdir(parents=True, exist_ok=True)
    path = _day_path(date_str)

    # 先清掉旧文件（覆盖写入）
    if path.exists():
        path.unlink()

    for i, d in enumerate(decisions):
        claim = d.get("claim", "").strip()
        # 去重：相同的命题只保留一次
        claim_key = claim.lower()
        if claim_key in seen_claims:
            continue
        seen_claims.add(claim_key)

        record = {
            "id": f"{date_str}-{len(enriched):03d}",
            "date": date_str,
            "claim": d.get("claim", ""),
            "direction": d.get("direction", "neutral"),
            "subject": d.get("subject", ""),
            "timeframe": d.get("timeframe", "short-term"),
            "source_type": d.get("source_type", ""),
            "confidence": d.get("confidence", "implied"),
            "extracted_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            # 校验字段（后续填充）
            "verdict": None,
            "verdict_note": None,
            "verified_at": None,
            "user_action": None,  # did_i_act / did_i_not_act / n_a
            "user_note": None,
        }
        enriched.append(record)

    with path.open("w", encoding="utf-8") as f:
        for r in enriched:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[decision_tracker] {date_str} 提取 {len(enriched)} 条命题", file=sys.stderr)
    return enriched


# ── 校验 ────────────────────────────────────────────────

def _collect_market_context(decisions: List[Dict]) -> str:
    """根据决策列表，收集相关的市场实际数据供 AI 校验。

    收集策略：
    - 总是拉 A 股主要指数（上证/深证/创业板）次日表现
    - 如果涉及港股 → 拉恒指/恒科
    - 如果涉及南下资金 → 拉资金流数据
    """
    lines = []
    subjects_lower = " ".join(d.get("subject", "") for d in decisions).lower()

    # A 股核心指数（次日）
    try:
        raw = ds.sina_realtime(["s_sh000001", "s_sz399001", "s_sz399006"])
        for line in raw:
            info = ds.parse_index_simple(line)
            if info:
                lines.append(f"A股指数 {info['name']}: {info['close']:.2f} ({info['pct']:+.2f}%)")
    except Exception as e:
        lines.append(f"A股指数获取失败: {e}")

    # 港股（如需）
    if any(kw in subjects_lower for kw in ["港股", "恒指", "恒生", "hsi", "腾讯", "美团", "小米"]):
        try:
            raw = ds.sina_realtime(["rt_hkHSI", "rt_hkHSCEI", "rt_hkHSTECH"])
            for line in raw:
                info = ds.parse_index_simple(line)
                if info:
                    lines.append(f"港股指数 {info['name']}: {info['close']:.2f} ({info['pct']:+.2f}%)")
        except Exception as e:
            lines.append(f"港股指数获取失败: {e}")

    # 美股（如需）—— 从 subject 中提取提到的美股代码
    us_stocks_mentioned = set()
    us_ticker_map = {
        "tsla": "usr_tsla", "tesla": "usr_tsla",
        "nvda": "usr_nvda", "nvidia": "usr_nvda",
        "amd": "usr_amd",
        "mrvl": "usr_mrvl", "marvell": "usr_mrvl",
        "mu": "usr_mu", "美光": "usr_mu", "micron": "usr_mu",
        "aapl": "usr_aapl", "apple": "usr_aapl", "苹果": "usr_aapl",
        "goog": "usr_goog", "google": "usr_goog", "谷歌": "usr_goog",
        "msft": "usr_msft", "microsoft": "usr_msft", "微软": "usr_msft",
        "amzn": "usr_amzn", "amazon": "usr_amzn", "亚马逊": "usr_amzn",
        "meta": "usr_meta",
        "pltr": "usr_pltr", "palantir": "usr_pltr",
    }
    for kw, code in us_ticker_map.items():
        if kw in subjects_lower:
            us_stocks_mentioned.add(code)

    if us_stocks_mentioned:
        try:
            raw = ds.sina_realtime(list(us_stocks_mentioned))
            for line in raw:
                # 美股格式: 名称,现价,涨跌幅%,时间,涨跌额,昨收?,最高,最低,52周高,52周低,...
                # 与 A 股 parse_stock 字段顺序不同，手动解析
                m = re.search(r'"([^"]+)"', line)
                if not m:
                    continue
                parts = m.group(1).split(",")
                if len(parts) < 4:
                    continue
                try:
                    name = parts[0]
                    price = float(parts[1])
                    pct = float(parts[2])
                    direction = "🟢" if pct >= 0.5 else ("🔴" if pct <= -0.5 else "⚪")
                    lines.append(
                        f"美股 {name}: ${price:.2f} ({pct:+.2f}%) {direction}"
                    )
                except (ValueError, IndexError):
                    continue
        except Exception as e:
            lines.append(f"美股数据获取失败: {e}")

    # 南下资金（如需）
    if any(kw in subjects_lower for kw in ["南下", "南向", "港股通"]):
        try:
            latest = ds.fetch_south_flow_latest()
            if latest:
                lines.append(
                    f"南下资金净买入: {latest['net_yi']:.2f} 亿元 "
                    f"({latest['date']})"
                )
            trend = ds.fetch_south_flow_trend(days=5)
            if trend:
                trend_str = " → ".join(
                    f"{t['date'][-5:]}:{t['net_yi']:+.1f}亿" for t in trend
                )
                lines.append(f"南下资金 5 日趋势: {trend_str}")
        except Exception as e:
            lines.append(f"南下资金获取失败: {e}")

    if not lines:
        return "（无市场数据可用）"
    return "\n".join(lines)


_VERIFY_PROMPT = """你是一个金融决策复盘系统。比对"预测/判断"与"市场实际结果"，给出裁决。

## 裁决标准
- **hit**：预测方向与实际走势一致
- **miss**：预测方向与实际走势相反
- **partial**：部分正确（方向对但幅度不够 / 时间窗口偏移 / 条件未完全满足）
- **n_a**：无法检验（数据不足 / 时限未到 / 命题太模糊）

## 重要原则
1. 宽容判断——"关注 xx 板块"如果板块涨了就是 hit（说明关注对了）
2. 不看幅度只看方向——涨 0.1% 也是 bullish hit
3. "企稳" = neutral 方向正确 → 横盘或微涨微跌都算 hit
4. 日内判断 → 看当日收盘 vs 开盘
5. 次日判断 → 看次日收盘 vs 当日收盘

## 输出格式
返回 JSON 数组，每个元素在原始基础上补充：
{
  "id": "原 ID",
  "verdict": "hit|miss|partial|n_a",
  "verdict_note": "一句话说明为什么（30 字内）"
}

只返回 JSON 数组，不要其他文字。"""


def verify_decisions(date_str: str, reference_date: Optional[str] = None) -> List[Dict]:
    """校验某天的决策命题。

    Args:
        date_str: 决策日期
        reference_date: 参考市场数据的日期（默认今天，即"用今天的数据检验昨天的决策"）

    Returns:
        list[dict] 带 verdict 的决策列表（已持久化）
    """
    path = _day_path(date_str)
    if not path.exists():
        # 先提取
        decisions = extract_decisions(date_str)
    else:
        decisions = _read_decisions(date_str)

    if not decisions:
        return []

    ref_date = reference_date or datetime.now().strftime("%Y-%m-%d")
    market_ctx = _collect_market_context(decisions)

    # 构造 prompt
    claims_json = json.dumps(
        [{"id": d["id"], "claim": d["claim"], "direction": d["direction"],
          "subject": d["subject"], "timeframe": d["timeframe"]} for d in decisions],
        ensure_ascii=False, indent=2,
    )

    prompt = (
        f"{_VERIFY_PROMPT}\n\n"
        f"## 决策日期\n{date_str}\n\n"
        f"## 校验日期（市场数据截止日）\n{ref_date}\n\n"
        f"## 市场实际数据\n{market_ctx}\n\n"
        f"## 待校验命题\n{claims_json}"
    )

    result = ai_chat(prompt, temperature=0.2, max_tokens=2000, timeout=90)
    if not result:
        print("[decision_tracker] AI 校验失败", file=sys.stderr)
        return decisions

    try:
        text = result.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[:-3]
        verdicts = json.loads(text)
    except json.JSONDecodeError:
        print(f"[decision_tracker] 校验结果 JSON 解析失败: {result[:200]}", file=sys.stderr)
        return decisions

    if not isinstance(verdicts, list):
        return decisions

    # 合并 verdict 到原始 decisions
    verdict_map = {v["id"]: v for v in verdicts}
    for d in decisions:
        v = verdict_map.get(d["id"], {})
        d["verdict"] = v.get("verdict")
        d["verdict_note"] = v.get("verdict_note")
        d["verified_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # 写回
    _write_decisions(date_str, decisions)
    print(f"[decision_tracker] {date_str} 校验完成: {_verdict_stats(decisions)}", file=sys.stderr)
    return decisions


# ── 用户标记 ─────────────────────────────────────────────

def mark_decision(decision_id: str, verdict: Optional[str] = None,
                  user_action: Optional[str] = None, user_note: Optional[str] = None) -> bool:
    """手动标记某条决策。

    Args:
        decision_id: 如 "2026-07-06-003"
        verdict: 手动覆写裁决
        user_action: did_i_act / did_i_not_act / n_a
        user_note: 自由备注
    """
    date_str = decision_id[:10]
    decisions = _read_decisions(date_str)
    found = False
    for d in decisions:
        if d["id"] == decision_id:
            if verdict:
                d["verdict"] = verdict
            if user_action:
                d["user_action"] = user_action
            if user_note:
                d["user_note"] = user_note
            found = True
            break

    if not found:
        print(f"[decision_tracker] 未找到决策 {decision_id}", file=sys.stderr)
        return False

    _write_decisions(date_str, decisions)
    return True


# ── 复盘报告 ─────────────────────────────────────────────

def format_weekly_review(start_date: str, end_date: Optional[str] = None) -> str:
    """生成周报复盘 Markdown。

    Args:
        start_date: 起始日期 YYYY-MM-DD
        end_date: 结束日期（默认今天）
    """
    end_date = end_date or datetime.now().strftime("%Y-%m-%d")

    # 收集日期范围内的所有决策
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    all_decisions = []
    cursor = start
    while cursor <= end:
        ds_str = cursor.strftime("%Y-%m-%d")
        all_decisions.extend(_read_decisions(ds_str))
        cursor += timedelta(days=1)

    if not all_decisions:
        return f"# 📊 周报复盘 · {start_date} → {end_date}\n\n> 本周暂无决策记录。\n"

    # 统计
    total = len(all_decisions)
    verified = [d for d in all_decisions if d.get("verdict")]
    hits = [d for d in verified if d["verdict"] == "hit"]
    misses = [d for d in verified if d["verdict"] == "miss"]
    partials = [d for d in verified if d["verdict"] == "partial"]
    n_a = [d for d in verified if d["verdict"] == "n_a"]

    hit_rate = len(hits) / max(len(verified), 1) * 100

    # 构建报告
    lines = [
        f"# 📊 周报复盘 · {start_date} → {end_date}",
        "",
        "## 🎯 准确率",
        "",
        f"| 指标 | 数值 |",
        f"|---|---|",
        f"| 总命题数 | {total} |",
        f"| 已校验 | {len(verified)} |",
        f"| ✅ 命中 | {len(hits)} |",
        f"| ❌ 失误 | {len(misses)} |",
        f"| ⚠️ 部分正确 | {len(partials)} |",
        f"| ➖ 无法判断 | {len(n_a)} |",
        f"| **命中率** | **{hit_rate:.0f}%** |",
        "",
    ]

    # 按来源统计
    by_source = {}
    for d in verified:
        src = d.get("source_type", "unknown")
        if src not in by_source:
            by_source[src] = {"total": 0, "hit": 0, "miss": 0}
        by_source[src]["total"] += 1
        if d["verdict"] == "hit":
            by_source[src]["hit"] += 1
        elif d["verdict"] == "miss":
            by_source[src]["miss"] += 1

    if by_source:
        lines.extend([
            "## 📡 按推送来源",
            "",
            "| 来源 | 总数 | 命中 | 失误 | 命中率 |",
            "|---|---|---|---|---|",
        ])
        for src, stats in sorted(by_source.items(), key=lambda x: -x[1]["total"]):
            rate = stats["hit"] / max(stats["total"], 1) * 100
            lines.append(
                f"| `{src}` | {stats['total']} | {stats['hit']} | "
                f"{stats['miss']} | {rate:.0f}% |"
            )
        lines.append("")

    # 失误清单
    if misses:
        lines.extend([
            "## ❌ 失误清单",
            "",
        ])
        for d in misses:
            lines.append(f"- **[{d['id']}]** {d['claim']}")
            if d.get("verdict_note"):
                lines.append(f"  → {d['verdict_note']}")
            if d.get("user_note"):
                lines.append(f"  → 💬 {d['user_note']}")
        lines.append("")

    # 亮点
    if hits:
        lines.extend([
            "## ✅ 命中亮点",
            "",
        ])
        for d in hits[:5]:  # 最多 5 条
            lines.append(f"- **[{d['id']}]** {d['claim']} — {d.get('verdict_note', '')}")
        lines.append("")

    # 用户操作统计
    acted = [d for d in all_decisions if d.get("user_action") == "did_i_act"]
    not_acted = [d for d in all_decisions if d.get("user_action") == "did_i_not_act"]
    if acted or not_acted:
        lines.extend([
            "## 🎮 执行情况",
            "",
            f"- 已执行操作: {len(acted)} 次",
            f"- 未执行操作: {len(not_acted)} 次",
            "",
        ])

    # 复盘区（待填）
    lines.extend([
        "---",
        "",
        "## 📝 本周心得",
        "",
        "> 待回填：哪些推送真正帮到了？哪些是噪音？学到了什么？",
        "",
        "- **最准的判断**：",
        "- **最大的失误**：",
        "- **本周教训**：",
        "- **下周注意**：",
        "",
    ])

    return "\n".join(lines)


# ── 辅助 ─────────────────────────────────────────────────

def _read_decisions(date_str: str) -> List[Dict]:
    path = _day_path(date_str)
    if not path.exists():
        return []
    decisions = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                decisions.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return decisions


def _write_decisions(date_str: str, decisions: List[Dict]):
    path = _day_path(date_str)
    _DECISIONS_ROOT.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for d in decisions:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def _verdict_stats(decisions: List[Dict]) -> str:
    total = len(decisions)
    hits = sum(1 for d in decisions if d.get("verdict") == "hit")
    misses = sum(1 for d in decisions if d.get("verdict") == "miss")
    partials = sum(1 for d in decisions if d.get("verdict") == "partial")
    n_a = sum(1 for d in decisions if d.get("verdict") == "n_a")
    unverified = total - hits - misses - partials - n_a
    return f"{total}条: ✅{hits} ❌{misses} ⚠️{partials} ➖{n_a} ◻️{unverified}"


def list_decisions(date_str: Optional[str] = None) -> List[Dict]:
    """列出某天的所有决策（用于 CLI 展示）"""
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    return _read_decisions(date_str)


def week_date_range() -> tuple:
    """返回本周一和今天的日期字符串"""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
