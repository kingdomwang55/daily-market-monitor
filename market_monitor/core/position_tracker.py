"""仓位健康度追踪（Position Health Tracker）

碧树西风风格：以月薪为锚，量化每笔回撤对生活的冲击。

核心概念：
- 单笔回撤 = (entry_price - current_price) / entry_price * current_shares * entry_price
  即绝对金额亏损（按成本计）
- 单笔回撤占月薪比 = 亏损金额 / monthly_salary
- 组合总回撤 = 所有持仓回撤之和
- 盈亏比 = (add_position - entry_price) / (entry_price - stop_loss)
  即潜在盈利空间 / 潜在亏损空间

数据文件：~/projects/market-monitor/positions.json
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# positions.json 默认路径
_POSITIONS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "positions.json",
)


# ── 读写 positions.json ────────────────────────────────────

def _default_data() -> Dict[str, Any]:
    """空数据骨架"""
    return {
        "monthly_salary": 0,
        "max_drawdown_months": 1,
        "positions": [],
        "cash_ratio": 0.0,
        "total_capital": 0,
    }


def load_positions(path: Optional[str] = None) -> Dict[str, Any]:
    """读取 positions.json。

    文件不存在或解析失败时返回空骨架，不抛异常。

    Args:
        path: 自定义文件路径，默认用 _POSITIONS_FILE

    Returns:
        数据字典，至少包含 monthly_salary / max_drawdown_months /
        positions / cash_ratio / total_capital
    """
    filepath = path or _POSITIONS_FILE
    if not os.path.exists(filepath):
        return _default_data()
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 兜底：确保关键字段存在
        base = _default_data()
        base.update(data)
        return base
    except (json.JSONDecodeError, OSError) as e:
        print(f"[position_tracker] 读取 {filepath} 失败: {e}", file=sys.stderr)
        return _default_data()


def save_positions(data: Dict[str, Any], path: Optional[str] = None) -> bool:
    """保存数据到 positions.json。

    Args:
        data: 完整数据字典
        path: 自定义文件路径

    Returns:
        True 成功 / False 失败
    """
    filepath = path or _POSITIONS_FILE
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except OSError as e:
        print(f"[position_tracker] 保存 {filepath} 失败: {e}", file=sys.stderr)
        return False


# ── 核心计算 ────────────────────────────────────────────────

def calc_position_health(
    positions_data: Dict[str, Any],
    current_prices: Dict[str, float],
) -> Dict[str, Any]:
    """计算仓位健康度。

    Args:
        positions_data: load_positions() 返回的完整数据
        current_prices: {position_id: current_price} 当前价格字典

    Returns:
        健康度报告字典，结构：
        {
            "monthly_salary": float,
            "max_drawdown_months": float,
            "total_capital": float,
            "cash_ratio": float,
            "positions": [
                {
                    "id", "name", "entry_price", "current_price",
                    "current_shares", "stop_loss", "add_position",
                    "entry_date", "note",
                    "market_value": float,        # 当前市值
                    "cost_value": float,          # 成本市值
                    "drawdown_amount": float,     # 回撤金额(正=亏)
                    "drawdown_pct": float,        # 回撤百分比
                    "drawdown_salary_ratio": float, # 占月薪比
                    "concentration": float,       # 仓位集中度
                    "risk_reward_ratio": float,   # 盈亏比
                    "pnl_pct": float,             # 当前盈亏百分比
                },
            ],
            "total_market_value": float,
            "total_cost_value": float,
            "total_drawdown": float,
            "total_drawdown_salary_ratio": float,
        }
    """
    monthly_salary = float(positions_data.get("monthly_salary", 0) or 0)
    max_dd_months = float(positions_data.get("max_drawdown_months", 1) or 1)
    cash_ratio = float(positions_data.get("cash_ratio", 0) or 0)
    total_capital = float(positions_data.get("total_capital", 0) or 0)
    positions = positions_data.get("positions", []) or []

    # 第一轮：算每只持仓的市值
    pos_details: List[Dict[str, Any]] = []
    total_market_value = 0.0
    total_cost_value = 0.0

    for pos in positions:
        pid = pos.get("id", "")
        entry_price = float(pos.get("entry_price", 0) or 0)
        shares = float(pos.get("current_shares", 0) or 0)
        cur_price = float(current_prices.get(pid, entry_price) or entry_price)

        market_value = cur_price * shares
        cost_value = entry_price * shares
        total_market_value += market_value
        total_cost_value += cost_value

        pos_details.append({
            "id": pid,
            "name": pos.get("name", ""),
            "entry_price": entry_price,
            "current_price": cur_price,
            "current_shares": shares,
            "stop_loss": float(pos.get("stop_loss", 0) or 0),
            "add_position": float(pos.get("add_position", 0) or 0),
            "entry_date": pos.get("entry_date", ""),
            "note": pos.get("note", ""),
            "market_value": market_value,
            "cost_value": cost_value,
        })

    # 第二轮：回撤、集中度、盈亏比
    total_drawdown = 0.0
    for pd in pos_details:
        entry = pd["entry_price"]
        cur = pd["current_price"]
        shares = pd["current_shares"]
        cost_val = pd["cost_value"]

        # 回撤金额（正 = 亏损）
        drawdown_amount = (entry - cur) * shares
        # 回撤百分比（基于成本）
        drawdown_pct = ((entry - cur) / entry * 100) if entry > 0 else 0.0
        # 当前盈亏百分比
        pnl_pct = ((cur - entry) / entry * 100) if entry > 0 else 0.0
        # 占月薪比
        dd_salary_ratio = (drawdown_amount / monthly_salary * 100) if monthly_salary > 0 else 0.0
        # 集中度
        concentration = (pd["market_value"] / total_market_value * 100) if total_market_value > 0 else 0.0
        # 盈亏比 = (add_position - entry_price) / (entry_price - stop_loss)
        stop_loss = pd["stop_loss"]
        add_pos = pd["add_position"]
        potential_profit = add_pos - entry
        potential_loss = entry - stop_loss
        rr_ratio = (potential_profit / potential_loss) if potential_loss > 0 else 0.0

        pd["drawdown_amount"] = drawdown_amount
        pd["drawdown_pct"] = drawdown_pct
        pd["drawdown_salary_ratio"] = dd_salary_ratio
        pd["concentration"] = concentration
        pd["risk_reward_ratio"] = rr_ratio
        pd["pnl_pct"] = pnl_pct

        total_drawdown += drawdown_amount

    total_dd_salary_ratio = (total_drawdown / monthly_salary * 100) if monthly_salary > 0 else 0.0

    return {
        "monthly_salary": monthly_salary,
        "max_drawdown_months": max_dd_months,
        "total_capital": total_capital,
        "cash_ratio": cash_ratio,
        "positions": pos_details,
        "total_market_value": total_market_value,
        "total_cost_value": total_cost_value,
        "total_drawdown": total_drawdown,
        "total_drawdown_salary_ratio": total_dd_salary_ratio,
    }


# ── 格式化报告 ──────────────────────────────────────────────

def _fmt_price(v: float) -> str:
    """智能价格格式化（大数字保留整数，小数字保留 2-3 位）"""
    av = abs(v)
    if av >= 100:
        return f"{v:,.0f}"
    if av >= 10:
        return f"{v:,.2f}"
    return f"{v:,.3f}"


def _fmt_money(v: float) -> str:
    """金额格式化（保留整数）"""
    return f"{v:,.0f}"


def format_health_report(health: Dict[str, Any]) -> str:
    """格式化仓位健康度报告（给盘后报告用）。

    Args:
        health: calc_position_health() 返回的字典

    Returns:
        多行文本，适合直接拼入盘后报告
    """
    positions = health.get("positions", [])
    if not positions:
        return "📊 仓位健康度\n━━━━━━━━━━━━━━━\n（无持仓数据）"

    monthly_salary = health["monthly_salary"]
    cash_ratio = health["cash_ratio"]
    total_capital = health["total_capital"]
    total_mv = health["total_market_value"]

    lines = [
        "📊 仓位健康度",
        "━━━━━━━━━━━━━━━",
        f"💰 总投入: ¥{total_capital:,.0f} | 现金比: {cash_ratio*100:.0f}%",
        f"📈 持仓数: {len(positions)} | 月薪锚: ¥{monthly_salary:,.0f}",
        "",
        "持仓明细:",
    ]

    for i, pd in enumerate(positions, 1):
        entry = pd["entry_price"]
        cur = pd["current_price"]
        shares = pd["current_shares"]
        stop_loss = pd["stop_loss"]
        add_pos = pd["add_position"]
        dd_amt = pd["drawdown_amount"]
        dd_pct = pd["drawdown_pct"]
        dd_sr = pd["drawdown_salary_ratio"]
        conc = pd["concentration"]
        rr = pd["risk_reward_ratio"]
        pnl_pct = pd["pnl_pct"]

        # 盈亏符号
        pnl_icon = "📈" if pnl_pct >= 0 else "📉"
        dd_icon = "✅" if dd_amt <= 0 else "⚠️"

        lines.append(
            f"{i}. {pd['name']} | {int(shares)}股 @ ¥{_fmt_price(entry)}"
        )
        # 回撤显示：正值=亏损 ⚠️，负值=浮盈 ✅（换成浮盈符号更清晰）
        if dd_amt > 0:
            dd_display = f"¥{_fmt_money(dd_amt)} {dd_icon}"
            dd_ratio_display = f"占月薪: {dd_sr:.1f}%"
        else:
            dd_display = f"浮盈 ¥{_fmt_money(-dd_amt)} ✅"
            dd_ratio_display = f"占月薪: {-dd_sr:.1f}%"
        lines.append(
            f"   {pnl_icon} 当前: ¥{_fmt_price(cur)} ({pnl_pct:+.1f}%) | "
            f"{dd_display} | {dd_ratio_display}"
        )
        # 止损 / 加仓
        sl_pct = ((stop_loss - entry) / entry * 100) if entry > 0 else 0.0
        ap_pct = ((add_pos - entry) / entry * 100) if entry > 0 else 0.0
        rr_icon = "✅" if rr >= 2 else "🟡"
        lines.append(
            f"   止损: ¥{_fmt_price(stop_loss)} ({sl_pct:+.1f}%) | "
            f"加仓: ¥{_fmt_price(add_pos)} ({ap_pct:+.1f}%)"
        )
        lines.append(
            f"   盈亏比: {rr:.1f} {rr_icon} | 集中度: {conc:.1f}%"
        )

    # 纪律检查
    lines.append("")
    lines.append("纪律检查:")
    checks = check_discipline(health)
    for c in checks:
        lines.append(c)

    return "\n".join(lines)


# ── 纪律检查 ────────────────────────────────────────────────

def check_discipline(health: Dict[str, Any]) -> List[str]:
    """纪律检查，返回检查结果文本列表。

    检查项：
    - 单笔回撤 > 月薪 * max_drawdown_months → 🔴 超限警告
    - 组合回撤 > 月薪 * max_drawdown_months → 🔴 组合超限
    - 仓位集中度 > 20% → 🟡 集中度过高
    - 现金比 < 20% → 🟡 现金不足
    - 盈亏比 < 2 → 🟡 盈亏比不达标

    Args:
        health: calc_position_health() 返回的字典

    Returns:
        检查结果文本列表，每条一行
    """
    results: List[str] = []
    monthly_salary = health["monthly_salary"]
    max_dd_months = health["max_drawdown_months"]
    cash_ratio = health["cash_ratio"]
    max_dd_amount = monthly_salary * max_dd_months

    # 单笔回撤检查
    single_exceeded = []
    for pd in health["positions"]:
        if pd["drawdown_amount"] > max_dd_amount and max_dd_amount > 0:
            single_exceeded.append(
                f"🔴 {pd['name']} 回撤 ¥{pd['drawdown_amount']:,.0f} "
                f"> 月薪×{max_dd_months:.0f}个月 (¥{max_dd_amount:,.0f})"
            )
    if single_exceeded:
        results.extend(single_exceeded)
    else:
        results.append("✅ 单笔回撤均在限额内")

    # 组合回撤检查
    total_dd = health["total_drawdown"]
    if total_dd > max_dd_amount and max_dd_amount > 0:
        results.append(
            f"🔴 组合回撤 ¥{total_dd:,.0f} > 月薪×{max_dd_months:.0f}个月 (¥{max_dd_amount:,.0f})"
        )
    else:
        results.append("✅ 组合回撤在限额内")

    # 集中度检查
    conc_exceeded = []
    for pd in health["positions"]:
        if pd["concentration"] > 20:
            conc_exceeded.append(
                f"🟡 {pd['name']}集中度 {pd['concentration']:.1f}% > 20%"
            )
    if conc_exceeded:
        results.extend(conc_exceeded)
    else:
        results.append("✅ 仓位集中度均 ≤ 20%")

    # 现金比检查
    if cash_ratio < 0.2:
        results.append(f"🟡 现金比 {cash_ratio*100:.0f}% < 20%")
    else:
        results.append(f"✅ 现金比 {cash_ratio*100:.0f}% ≥ 20%")

    # 盈亏比检查
    rr_failed = []
    for pd in health["positions"]:
        if pd["risk_reward_ratio"] < 2 and pd["risk_reward_ratio"] > 0:
            rr_failed.append(
                f"🟡 {pd['name']}盈亏比 {pd['risk_reward_ratio']:.1f} < 2"
            )
    if rr_failed:
        results.extend(rr_failed)
    else:
        results.append("✅ 盈亏比均 ≥ 2")

    return results


# ── AI 摘要 ─────────────────────────────────────────────────

def signals_summary_for_ai(health: Dict[str, Any]) -> str:
    """给 AI prompt 用的精简摘要。

    Args:
        health: calc_position_health() 返回的字典

    Returns:
        紧凑文本，可直接注入 AI prompt
    """
    positions = health.get("positions", [])
    if not positions:
        return "【仓位健康度】无持仓数据"

    lines = ["【仓位健康度】"]
    lines.append(
        f"月薪锚: ¥{health['monthly_salary']:,.0f} | "
        f"最大回撤月数: {health['max_drawdown_months']:.0f} | "
        f"现金比: {health['cash_ratio']*100:.0f}%"
    )

    for pd in positions:
        dd = pd["drawdown_amount"]
        dd_sr = pd["drawdown_salary_ratio"]
        conc = pd["concentration"]
        rr = pd["risk_reward_ratio"]
        pnl = pd["pnl_pct"]
        lines.append(
            f"- {pd['name']}: 当前¥{_fmt_price(pd['current_price'])}({pnl:+.1f}%), "
            f"回撤¥{_fmt_money(dd)}(占月薪{dd_sr:.1f}%), "
            f"集中度{conc:.1f}%, 盈亏比{rr:.1f}"
        )

    total_dd = health["total_drawdown"]
    total_dd_sr = health["total_drawdown_salary_ratio"]
    lines.append(
        f"组合总回撤: ¥{total_dd:,.0f} (占月薪{total_dd_sr:.1f}%)"
    )

    # 纪律违规摘要
    checks = check_discipline(health)
    violations = [c for c in checks if c.startswith("🔴") or c.startswith("🟡")]
    if violations:
        lines.append("纪律警告: " + "; ".join(v.replace("🔴 ", "").replace("🟡 ", "") for v in violations))
    else:
        lines.append("纪律检查: 全部通过 ✅")

    return "\n".join(lines)


# ── 持仓管理（增删改） ──────────────────────────────────────

def _gen_id(name: str) -> str:
    """根据名称生成简易 ID"""
    # 用拼音首字母太复杂，这里用 name + 时间戳后4位
    import hashlib
    h = hashlib.md5(name.encode("utf-8")).hexdigest()[:6]
    return f"pos_{h}"


def add_position(
    name: str,
    entry_price: float,
    shares: int,
    stop_loss: float,
    add_position_price: float,
    note: str = "",
    pos_id: Optional[str] = None,
    entry_date: Optional[str] = None,
    path: Optional[str] = None,
) -> Tuple[bool, str]:
    """添加持仓。

    Args:
        name: 持仓名称
        entry_price: 入场价
        shares: 股数
        stop_loss: 止损价
        add_position_price: 加仓价
        note: 备注
        pos_id: 自定义 ID，不传则自动生成
        entry_date: 入场日期 YYYY-MM-DD，不传则今天
        path: positions.json 路径

    Returns:
        (success, message)
    """
    data = load_positions(path)
    pid = pos_id or _gen_id(name)

    # 检查 ID 是否已存在
    existing_ids = {p.get("id") for p in data.get("positions", [])}
    if pid in existing_ids:
        return False, f"持仓 ID '{pid}' 已存在"

    new_pos = {
        "id": pid,
        "name": name,
        "entry_price": float(entry_price),
        "current_shares": int(shares),
        "stop_loss": float(stop_loss),
        "add_position": float(add_position_price),
        "entry_date": entry_date or datetime.now().strftime("%Y-%m-%d"),
        "note": note,
    }
    data.setdefault("positions", []).append(new_pos)
    if save_positions(data, path):
        return True, f"已添加持仓: {name} (ID: {pid})"
    return False, "保存失败"


def remove_position(pos_id: str, path: Optional[str] = None) -> Tuple[bool, str]:
    """删除持仓。

    Args:
        pos_id: 持仓 ID
        path: positions.json 路径

    Returns:
        (success, message)
    """
    data = load_positions(path)
    positions = data.get("positions", [])
    before = len(positions)
    data["positions"] = [p for p in positions if p.get("id") != pos_id]
    if len(data["positions"]) == before:
        return False, f"未找到持仓 ID '{pos_id}'"
    if save_positions(data, path):
        return True, f"已删除持仓: {pos_id}"
    return False, "保存失败"


def update_position(pos_id: str, path: Optional[str] = None, **kwargs) -> Tuple[bool, str]:
    """更新持仓字段。

    支持更新的字段：name, entry_price, current_shares, stop_loss,
    add_position, entry_date, note

    Args:
        pos_id: 持仓 ID
        path: positions.json 路径
        **kwargs: 要更新的字段

    Returns:
        (success, message)
    """
    allowed_fields = {
        "name", "entry_price", "current_shares", "stop_loss",
        "add_position", "entry_date", "note",
    }
    invalid = set(kwargs.keys()) - allowed_fields
    if invalid:
        return False, f"不支持的字段: {', '.join(invalid)}"

    data = load_positions(path)
    found = False
    for p in data.get("positions", []):
        if p.get("id") == pos_id:
            for k, v in kwargs.items():
                p[k] = v
            found = True
            break
    if not found:
        return False, f"未找到持仓 ID '{pos_id}'"
    if save_positions(data, path):
        return True, f"已更新持仓: {pos_id} ({', '.join(kwargs.keys())})"
    return False, "保存失败"


# ── 辅助：从 data_source 获取当前价格 ───────────────────────

def fetch_current_prices(positions_data: Dict[str, Any]) -> Dict[str, float]:
    """从 data_source 获取持仓的当前价格。

    需要在 positions.json 中为每个持仓提供 'symbol' 字段
    （如 sh510300），否则跳过。

    Args:
        positions_data: load_positions() 返回的数据

    Returns:
        {position_id: current_price}
    """
    prices: Dict[str, float] = {}
    positions = positions_data.get("positions", []) or []
    if not positions:
        return prices

    try:
        from market_monitor.core import data_source as ds
    except ImportError:
        # 独立运行时可能没有 data_source
        return prices

    for pos in positions:
        pid = pos.get("id", "")
        symbol = pos.get("symbol", "")
        if not symbol:
            continue
        q = ds.get_sina_quote(symbol)
        if q and q.get("close"):
            prices[pid] = q["close"]

    return prices
