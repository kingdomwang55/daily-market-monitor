"""shanghai_watch monitor 单元测试

验证 7 类触发条件都能正确识别。用 mock kline 避免依赖网络。
"""
from __future__ import annotations

import pytest

from market_monitor.monitors.shanghai_watch import ShanghaiWatchMonitor


def _mk_kline_entry(day: str, o: float, h: float, l: float, c: float, v: float):
    return {"day": day, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _build_base_kline(days: int = 260, start_close: float = 3900.0, vol_bh: float = 500.0):
    """构造 N 天的 kline，一律平稳走势 + 均匀量能。

    volume 单位是"手"，vol_bh 是"亿手"（乘 1e8 转回）。
    """
    kline = []
    for i in range(days):
        c = start_close + (i - days / 2) * 0.1  # 轻微线性
        kline.append(_mk_kline_entry(
            f"day{i:03d}",
            o=c - 2, h=c + 5, l=c - 5, c=c, v=vol_bh * 1e8,
        ))
    return kline


@pytest.fixture
def monitor():
    m = ShanghaiWatchMonitor.__new__(ShanghaiWatchMonitor)
    m.force = False
    m.snapshot = False
    return m


# --------------------------------------------------------
# ① V 型收回
# --------------------------------------------------------
def test_v_reversal_triggers(monitor):
    kline = _build_base_kline(days=260, start_close=3900.0, vol_bh=500.0)
    # 前一日预为 3830（确保今日 pct > -1），不影响 MA20/MA250
    kline[-2] = _mk_kline_entry(
        "P", o=3835, h=3840, l=3820, c=3830, v=500 * 1e8,
    )
    # 最后一根：低点 3780 触 3800 区，收盘 3820（V 型回收），量 780 亿手
    kline[-1] = _mk_kline_entry(
        "T", o=3830, h=3835, l=3780, c=3820, v=780 * 1e8,
    )
    metrics = monitor._build_metrics(kline)
    signals = monitor._check_signals(metrics)
    keys = [s["key"] for s in signals]
    assert "v_reversal" in keys, f"got {keys}"


def test_v_reversal_no_trigger_low_volume(monitor):
    """量能不够 750 亿不触发"""
    kline = _build_base_kline(days=260, start_close=3900.0, vol_bh=500.0)
    kline[-1] = _mk_kline_entry(
        "T", o=3830, h=3835, l=3780, c=3820, v=600 * 1e8,
    )
    metrics = monitor._build_metrics(kline)
    signals = monitor._check_signals(metrics)
    assert "v_reversal" not in [s["key"] for s in signals]


# --------------------------------------------------------
# ② 3800 区放量长下影
# --------------------------------------------------------
def test_hammer_at_3800_triggers(monitor):
    kline = _build_base_kline(days=260, start_close=3900.0, vol_bh=500.0)
    # 实体 5（3820→3825），下影 45（3820-3775），量 720 亿手
    kline[-1] = _mk_kline_entry(
        "T", o=3820, h=3826, l=3775, c=3825, v=720 * 1e8,
    )
    metrics = monitor._build_metrics(kline)
    signals = monitor._check_signals(metrics)
    assert "hammer_at_3800" in [s["key"] for s in signals]


# --------------------------------------------------------
# ③ 站回 MA250 连续 3 日
# --------------------------------------------------------
def test_ma250_hold_triggers(monitor):
    kline = _build_base_kline(days=260, start_close=3900.0, vol_bh=500.0)
    # 前 257 天正常，最后 3 天大力站上 MA250（大约 3900 → 抬到 4200）
    for i in [-3, -2, -1]:
        kline[i] = _mk_kline_entry(
            f"T{i}", o=4180, h=4210, l=4170, c=4200, v=600 * 1e8,
        )
    metrics = monitor._build_metrics(kline)
    signals = monitor._check_signals(metrics)
    keys = [s["key"] for s in signals]
    assert any(k.startswith("ma250_hold_") for k in keys), f"got {keys}"


# --------------------------------------------------------
# ④ MA250 反抽被拒
# --------------------------------------------------------
def test_ma250_reject_triggers(monitor):
    kline = _build_base_kline(days=260, start_close=3900.0, vol_bh=500.0)
    # 让近 5 日内至少一天收盘低于 MA250（触发 broke_ma250_recently）
    for i in [-6, -5, -4, -3, -2]:
        kline[i] = _mk_kline_entry(
            kline[i]["day"], o=3855, h=3860, l=3845, c=3850, v=600 * 1e8,
        )
    # 前日 close = 3950（高于 MA250～3899）
    kline[-2] = _mk_kline_entry(
        "P", o=3900, h=3960, l=3895, c=3950, v=600 * 1e8,
    )
    ma250 = sum(float(k["close"]) for k in kline[-250:]) / 250
    # 今 open 高开 3945， close 跌回 MA250 附近。今 close 需 pct < -1% 且 |c-ma250|/ma250 <= 0.005
    # 以 ma250 为基准，设 today_close = ma250 - 2（在 MA250 下方 0.05%）
    today_close = ma250 - 2  # ≈ 3897
    # pct = (today - 3950) / 3950 ≈ -1.3%
    kline[-1] = _mk_kline_entry(
        "T", o=3945, h=3948, l=today_close - 3,
        c=today_close, v=600 * 1e8,
    )
    metrics = monitor._build_metrics(kline)
    signals = monitor._check_signals(metrics)
    keys = [s["key"] for s in signals]
    assert "ma250_reject" in keys, (
        f"got {keys} metrics_ma250={metrics['ma250']:.2f} pct={metrics['pct']:.2f}% "
        f"broke_recently={metrics['broke_ma250_recently']}"
    )


# --------------------------------------------------------
# ⑤ 缩量破位 3800
# --------------------------------------------------------
def test_shrink_break_3800_triggers(monitor):
    kline = _build_base_kline(days=260, start_close=3900.0, vol_bh=500.0)
    kline[-1] = _mk_kline_entry(
        "T", o=3810, h=3815, l=3760, c=3780, v=350 * 1e8,  # 350 < 500 * 0.8
    )
    metrics = monitor._build_metrics(kline)
    signals = monitor._check_signals(metrics)
    assert "shrink_break_3800" in [s["key"] for s in signals]


# --------------------------------------------------------
# ⑥ 逼近止损 3700
# --------------------------------------------------------
def test_near_stop_3700_triggers(monitor):
    kline = _build_base_kline(days=260, start_close=3900.0, vol_bh=500.0)
    kline[-1] = _mk_kline_entry(
        "T", o=3730, h=3735, l=3705, c=3715, v=400 * 1e8,
    )
    metrics = monitor._build_metrics(kline)
    signals = monitor._check_signals(metrics)
    assert "near_stop_3700" in [s["key"] for s in signals]


# --------------------------------------------------------
# ⑦ 跌破止损 3700
# --------------------------------------------------------
def test_break_stop_3700_triggers(monitor):
    kline = _build_base_kline(days=260, start_close=3900.0, vol_bh=500.0)
    kline[-1] = _mk_kline_entry(
        "T", o=3700, h=3705, l=3660, c=3680, v=400 * 1e8,
    )
    metrics = monitor._build_metrics(kline)
    signals = monitor._check_signals(metrics)
    assert "break_stop_3700" in [s["key"] for s in signals]


# --------------------------------------------------------
# 无触发（当前市场状态）
# --------------------------------------------------------
def test_current_state_no_trigger(monitor):
    """模拟 2026-07-16 收盘：close=3882 low=3867 vol=535，
    应该无触发（还没到 3800）"""
    kline = _build_base_kline(days=260, start_close=3900.0, vol_bh=500.0)
    kline[-1] = _mk_kline_entry(
        "T", o=3950, h=3955, l=3867, c=3882, v=535 * 1e8,
    )
    metrics = monitor._build_metrics(kline)
    signals = monitor._check_signals(metrics)
    assert signals == [], f"unexpected trigger: {[s['key'] for s in signals]}"
