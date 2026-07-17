"""数据库种子数据

首次跑或 schema 重建后调用，把 monitor/symbol/signal_type 元数据灌进 registry。

用法：
    from market_monitor.data.seeds import run_seeds
    run_seeds()
或命令行：
    python -m market_monitor.data.seeds
"""
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_session
from .models import MonitorRegistry, SymbolRegistry, SignalTypeRegistry


# ═══════════════════════════════════════════════════
# Monitor 元数据（从 monitors/registry.py 手动同步一次）
# ═══════════════════════════════════════════════════

MONITORS = [
    # (name, display, category, description)
    ("stabilize",   "企稳信号 + 防御性资产", "periodic", "工作日 09:35-15:05 每 30 分钟（已停用，被 pulse 取代）"),
    ("us_market",   "美股夜盘监控",         "periodic", "工作日夜盘多档"),
    ("hk_market",   "港股盘中综合",         "periodic", "工作日 09:32-16:05 每 30 分钟（已停用，被 pulse 取代）"),
    ("shock",       "A 股异动预警",         "shock",    "A 股 10 分钟检查，触发才推"),
    ("hk_shock",    "港股异动预警",         "shock",    "港股 10 分钟检查 + A 股联动"),
    ("price_alert", "关键点位预警",         "alert",    "30 分钟检查止损/加仓位"),
    ("morning",     "晨间市场简报",         "report",   "工作日 07:00 全球市场"),
    ("evening",     "盘后总结",             "report",   "工作日 17:00 A 股盘后"),
    ("voice",       "语音播报",             "report",   "语音版市场简报"),
    ("macro",       "宏观事件跟踪",         "periodic", "宏观日历 + 跨资产联动"),
    ("review",      "周度复盘",             "report",   "周末复盘"),
    ("monthly",     "月度复盘",             "report",   "月末复盘"),
    ("midday",      "午间综述",             "periodic", "工作日 12:15 半日综述"),
    ("pulse",       "盘中脉搏",             "periodic", "工作日 10:30 / 14:00 条件优先"),
    ("shanghai_watch", "上证 3800 剧本",    "alert",    "上证 3800 剧本触发条件监控"),
    ("decision",    "AI 决策命题",          "research", "从推送日志抽取的可检验判断"),
]


# ═══════════════════════════════════════════════════
# Symbol 元数据（核心标的先灌，后续可增量）
# ═══════════════════════════════════════════════════

SYMBOLS = [
    # (symbol, display, market, asset_class, currency, source)
    # A 股指数
    ("sh000001",   "上证指数",   "CN", "index", "CNY", "sina"),
    ("s_sh000001", "上证指数",   "CN", "index", "CNY", "sina"),
    ("s_sz399006", "创业板指",   "CN", "index", "CNY", "sina"),
    ("s_sh000300", "沪深300",    "CN", "index", "CNY", "sina"),
    ("s_sz399001", "深证成指",   "CN", "index", "CNY", "sina"),
    ("s_sh000016", "上证50",     "CN", "index", "CNY", "sina"),
    # 港股指数
    ("hkHSI",      "恒生指数",   "HK", "index", "HKD", "sina"),
    ("hkHSCEI",    "恒生国企",   "HK", "index", "HKD", "sina"),
    ("hkHSTECH",   "恒生科技",   "HK", "index", "HKD", "sina"),
    # 港股通个股
    ("hk00700", "腾讯控股",       "HK", "stock", "HKD", "sina"),
    ("hk03690", "美团-W",         "HK", "stock", "HKD", "sina"),
    ("hk01810", "小米集团",       "HK", "stock", "HKD", "sina"),
    ("hk00981", "中芯国际",       "HK", "stock", "HKD", "sina"),
    ("hk01211", "比亚迪股份",     "HK", "stock", "HKD", "sina"),
    ("hk09988", "阿里巴巴-SW",    "HK", "stock", "HKD", "sina"),
    ("hk09618", "京东集团-SW",    "HK", "stock", "HKD", "sina"),
    # 美股指数（示意）
    ("gb_dji",    "道琼斯工业",   "US", "index", "USD", "sina"),
    ("gb_ixic",   "纳斯达克",     "US", "index", "USD", "sina"),
    ("gb_inx",    "标普500",      "US", "index", "USD", "sina"),
    # 商品
    ("hf_GC",     "COMEX 黄金",   "GOLD", "commodity", "USD", "sina"),
    ("nf_AU0",    "沪金主力",     "GOLD", "commodity", "CNY", "sina"),
    # 外汇
    ("fx_susdcnh", "USDCNH",      "FX", "fx", "USD", "sina"),
]


# ═══════════════════════════════════════════════════
# Signal 类型（先灌 hk_shock 的，其他后续增量）
# ═══════════════════════════════════════════════════

SIGNAL_TYPES = [
    # (signal_type, monitor, display, direction, description)
    # hk_shock ──────────────────────
    ("hk_resonance_down", "hk_shock", "港 A 共振下跌",  -1, "港股跌 + A 股同向跌"),
    ("hk_resonance_up",   "hk_shock", "港 A 共振上涨",   1, "港股涨 + A 股同向涨"),
    ("hk_only_down",      "hk_shock", "港股独跌",         -1, "港股跌 A 股不跌"),
    ("hk_only_up",        "hk_shock", "港股独涨",          1, "港股涨 A 股不涨"),
    ("hk_divergence",     "hk_shock", "港 A 分歧",         0, "港股 A 股反向"),
    ("hk_a_closed",       "hk_shock", "A 股已收盘",        0, "港股仍交易，A 股已收"),
    ("hk_a_not_open",     "hk_shock", "A 股未开盘",        0, "港股先行，A 股未开"),
    ("hk_neutral",        "hk_shock", "港股无异动",         0, "无明显异动"),

    # shock ──────────────────────────────
    ("shock_index_up_L1",    "shock",  "A 股指数弱涨 L1",   1, "指数涨幅进入 L1 阈值"),
    ("shock_index_up_L2",    "shock",  "A 股指数中涨 L2",   1, "指数涨幅进入 L2 阈值"),
    ("shock_index_up_L3",    "shock",  "A 股指数强涨 L3",   1, "指数涨幅进入 L3 阈值"),
    ("shock_index_down_L1",  "shock",  "A 股指数小跌 L1",  -1, "指数跌幅进入 L1 阈值"),
    ("shock_index_down_L2",  "shock",  "A 股指数中跌 L2",  -1, "指数跌幅进入 L2 阈值"),
    ("shock_index_down_L3",  "shock",  "A 股指数重跌 L3",  -1, "指数跌幅进入 L3 阈值"),
    ("shock_sector_only",    "shock",  "仅板块异动",       0, "大盘平稳但板块有异动"),
    ("shock_mixed_L1",       "shock",  "指数+板块异动 L1",  0, "大盘与板块同时异动"),
    ("shock_mixed_L2",       "shock",  "指数+板块异动 L2",  0, "大盘与板块同时异动"),
    ("shock_mixed_L3",       "shock",  "指数+板块异动 L3",  0, "大盘与板块同时异动"),
    ("shock_neutral",        "shock",  "A 股平稳",         0, "无明显异动"),

    # price_alert ─────────────────────────
    ("price_stop_break",  "price_alert", "跌破止损位",     -1, "价格跌破止损阈值"),
    ("price_add_break",   "price_alert", "突破加仓位",      1, "价格突破加仓阈值"),
    ("price_mixed_break", "price_alert", "多方向突破",      0, "同时触发多个阈值"),
    ("price_neutral",     "price_alert", "点位平稳",        0, "无阈值突破"),

    # pulse ──────────────────────────────
    ("pulse_index_up",      "pulse", "盘中指数拉升",    1, "指数 ≥ +1%"),
    ("pulse_index_down",    "pulse", "盘中指数回落",   -1, "指数 ≤ -1%"),
    ("pulse_near_key_level", "pulse", "逼近关键点位",   0, "距关键点位 ≤ 1%"),
    ("pulse_stabilize",     "pulse", "企稳信号命中",     1, "企稳信号 ≥ 2 个"),
    ("pulse_sector_move",   "pulse", "板块异动",         0, "板块 ≥ ±2%"),
    ("pulse_defensive",     "pulse", "避险资产异动",     0, "黏金/红利 ≥ ±1%"),
    ("pulse_other",         "pulse", "其他信号",         0, "其他触发条件"),
    ("pulse_heartbeat",     "pulse", "平淡心跳",         0, "无信号，一行心跳"),

    # shanghai_watch ────────────────────
    ("shanghai_v_reversal",       "shanghai_watch", "上证 V 型收回",       1, "3800 区 V 型收回"),
    ("shanghai_hammer_at_3800",   "shanghai_watch", "3800 放量长下影",     1, "3800 区放量长下影"),
    ("shanghai_ma250_hold",       "shanghai_watch", "连续站上 MA250",      1, "连续站上 MA250"),
    ("shanghai_ma250_reject",     "shanghai_watch", "MA250 反抽被拒",     -1, "MA250 附近反抽被拒"),
    ("shanghai_shrink_break_3800", "shanghai_watch", "缩量破位 3800",     -1, "缩量跌破 3800"),
    ("shanghai_near_stop_3700",   "shanghai_watch", "逼近止损 3700",     -1, "逼近 3700 止损位"),
    ("shanghai_break_stop_3700",  "shanghai_watch", "跌破止损 3700",     -1, "跌破 3700 止损位"),

    # decision ───────────────────────────
    ("decision_bullish", "decision", "AI 看多命题", 1, "AI 从推送提取的看多判断"),
    ("decision_bearish", "decision", "AI 看空命题", -1, "AI 从推送提取的看空判断"),
    ("decision_neutral", "decision", "AI 中性命题", 0, "AI 从推送提取的中性/关注判断"),
]


def _upsert_many(session: Session, model, rows: Iterable, pk_name: str):
    """按主键 upsert（新增 / 存在则更新非空字段）"""
    inserted = updated = 0
    for r in rows:
        pk_val = r[pk_name]
        obj = session.get(model, pk_val)
        if obj is None:
            session.add(model(**r))
            inserted += 1
        else:
            changed = False
            for k, v in r.items():
                if k == pk_name:
                    continue
                if v is not None and getattr(obj, k, None) != v:
                    setattr(obj, k, v)
                    changed = True
            if changed:
                updated += 1
    return inserted, updated


def run_seeds():
    """执行 seeds（幂等）"""
    monitors = [
        dict(name=n, display_name=d, category=c, description=desc)
        for n, d, c, desc in MONITORS
    ]
    symbols = [
        dict(symbol=s, display_name=d, market=m, asset_class=ac, currency=cur, data_source=src)
        for s, d, m, ac, cur, src in SYMBOLS
    ]
    signals = [
        dict(signal_type=s, monitor=m, display_name=d, direction=dir_, description=desc)
        for s, m, d, dir_, desc in SIGNAL_TYPES
    ]

    stats = {}
    with get_session() as s:
        i1, u1 = _upsert_many(s, MonitorRegistry, monitors, "name")
        i2, u2 = _upsert_many(s, SymbolRegistry, symbols, "symbol")
        i3, u3 = _upsert_many(s, SignalTypeRegistry, signals, "signal_type")
        stats["monitors"]     = {"inserted": i1, "updated": u1}
        stats["symbols"]      = {"inserted": i2, "updated": u2}
        stats["signal_types"] = {"inserted": i3, "updated": u3}
    return stats


if __name__ == "__main__":
    import json
    stats = run_seeds()
    print(json.dumps(stats, indent=2, ensure_ascii=False))


# 别名：与 CLI 保持兼容
seed_all = run_seeds
