"""上证 3800 剧本监控 (Shanghai 3800 Watch)

背景：基于 2026-07-16 的分析（notes/2026-07-16-shanghai-3800-entry-review.md），
上证进入 3800 附近的关键观察窗口。这个 monitor 专门盯以下 5 类触发条件：

【建仓/加仓触发（右侧机会）】
① V 型收回（3 月剧本复刻）：
   - 日内低点 ≤ 3800 且收盘 > 3800
   - 收盘涨幅 > -1%
   - 成交量 > 750 亿手（相对近 20 日均值放大 ≥ 30%）
   - → 强做多信号

② 放量长下影线：
   - 日内低点 ≤ 3820（3800 ± 20）
   - 下影 > 实体 × 2
   - 成交量 > 700 亿手
   - → 试探性建仓 1-2 成

③ 站回 MA250 连续 3 日：
   - 连续 3 个交易日收盘 ≥ MA250
   - → 加仓信号

【减仓/风控触发（左侧风险）】
④ MA250 反抽被拒：
   - 前 5 日内曾破 MA250
   - 反抽至 MA250 (±0.5%) 后当日收阴且跌幅 > -1%
   - → 减仓到 2 成

⑤ 缩量破位 3800：
   - 收盘 < 3800
   - 成交量 < 20 日均量 × 0.8（无恐慌盘）
   - → 空仓观望，下看 3600

⑥ 逼近止损 3700：
   - 收盘 ≤ 3730（±1%）
   - → 提前预警

⑦ 跌破止损 3700：
   - 收盘 < 3700
   - → 无条件清仓

⑧ 放量破位 3800（2026-07-17 实盘盲区修复）：
   - 收盘 < 3800
   - 成交量 > 20 日均量 × 1.10（放量 ≥ 10%）
   - 单日跌幅 < -2.5%
   - → 恐慌盘出货，筑底三段式第一段，不入场但盯紧缩量确认
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple

from ..core.base import BaseMonitor
from ..core import data_source as ds
from ..signals import Signal
from ..signals.persist import persist_signals


# ==========================================================
# 触发阈值（写在代码里，未来抽出到 config 也可以）
# ==========================================================
SH_SYMBOL = "sh000001"
KEY_LEVEL = 3800
KEY_STOP = 3700
MA250_TARGET = None  # 动态计算
VOL_HUGE_BILLION = 750  # V 型 / 站稳的放量阈值（亿手）
VOL_MEDIUM_BILLION = 700  # 长下影的量能阈值
VOL_SHRINK_RATIO = 0.8  # 缩量阈值（相对 20 日均量）
V_LOW_BAND = (3760, KEY_LEVEL)  # V 型触底带
LONG_HAMMER_LOW_MAX = 3820  # 长下影线的低点上限
LONG_HAMMER_SHADOW_BODY_RATIO = 2.0
NEAR_STOP_BAND = 30  # 距止损 30 点内预警
MA250_REJECT_TOL = 0.005  # MA250 反抽 ±0.5%

# ⑧ 放量破位 3800
VOL_BREAK_RATIO = 1.10  # 相对 20 日均量放大 10%（市场共识阈值）
VOL_BREAK_DAY_RATIO = 1.15  # 相对昨日量放大 15%（环比口径）
VOL_BREAK_PCT = -2.5    # 单日跌幅阈值


class ShanghaiWatchMonitor(BaseMonitor):
    """上证 3800 剧本监控"""

    name = "shanghai_watch"
    display_name = "上证 3800 剧本"

    # ------------------------------------------------------
    # 数据抓取 & 指标计算
    # ------------------------------------------------------
    def _fetch_kline(self, days: int = 280) -> List[Dict]:
        """拉日 K，若拿不到抛异常由 run 兜底"""
        kline = ds.get_kline(SH_SYMBOL, days=days)
        if len(kline) < 30:
            raise RuntimeError(f"K 线数据不足: {len(kline)} 条")
        return kline

    @staticmethod
    def _ma(values: List[float], n: int) -> Optional[float]:
        if len(values) < n:
            return None
        return sum(values[-n:]) / n

    @staticmethod
    def _to_billion_hand(volume: float) -> float:
        """新浪 K 线成交量单位是"手"（1手=100股），转成"亿手"

        注意：市场口语中"每日成交额 XXX 亿"通常指"亿元"。
        为保持 config/文档一致（Steven 分析报告用"亿手"），此处按手数×1e-8。
        实际 750 亿手 ≈ 沪深两市合计成交额约 1.5 万亿元，符合大盘量能量级。
        """
        return float(volume) / 1e8

    def _build_metrics(self, kline: List[Dict]) -> Dict:
        """从 kline 汇总关键指标"""
        latest = kline[-1]
        latest_close = float(latest["close"])
        latest_open = float(latest["open"])
        latest_high = float(latest["high"])
        latest_low = float(latest["low"])
        latest_vol_bh = self._to_billion_hand(latest["volume"])

        closes = [float(k["close"]) for k in kline]
        vols_bh = [self._to_billion_hand(k["volume"]) for k in kline]

        ma5 = self._ma(closes, 5)
        ma20 = self._ma(closes, 20)
        ma60 = self._ma(closes, 60)
        ma120 = self._ma(closes, 120)
        ma250 = self._ma(closes, 250)

        # 近 20 日均量（不含当日），用于判断"放量/缩量"
        vol_ma20_prev = None
        if len(vols_bh) >= 21:
            vol_ma20_prev = sum(vols_bh[-21:-1]) / 20

        # 连续站上 MA250 天数（含当日）
        ma250_hold_days = 0
        if ma250 is not None:
            for i in range(len(closes) - 1, -1, -1):
                if i < 249:
                    break
                window_ma = sum(closes[i - 249:i + 1]) / 250
                if closes[i] >= window_ma:
                    ma250_hold_days += 1
                else:
                    break

        # 近 5 日是否曾破 MA250（判断反抽）
        broke_ma250_recently = False
        if ma250 is not None and len(closes) >= 6:
            for i in range(len(closes) - 6, len(closes) - 1):
                if i >= 249:
                    ma250_i = sum(closes[i - 249:i + 1]) / 250
                    if closes[i] < ma250_i:
                        broke_ma250_recently = True
                        break

        # 前一日
        prev = kline[-2] if len(kline) >= 2 else None
        prev_close = float(prev["close"]) if prev else None
        prev_vol_bh = self._to_billion_hand(prev["volume"]) if prev else None
        pct = (latest_close - prev_close) / prev_close * 100 if prev_close else 0

        body = abs(latest_close - latest_open)
        lower_shadow = min(latest_close, latest_open) - latest_low
        upper_shadow = latest_high - max(latest_close, latest_open)

        return {
            "date": latest.get("day"),
            "close": latest_close,
            "open": latest_open,
            "high": latest_high,
            "low": latest_low,
            "prev_close": prev_close,
            "prev_vol_bh": prev_vol_bh,
            "pct": pct,
            "volume_bh": latest_vol_bh,
            "vol_ma20_prev": vol_ma20_prev,
            "ma5": ma5,
            "ma20": ma20,
            "ma60": ma60,
            "ma120": ma120,
            "ma250": ma250,
            "ma250_hold_days": ma250_hold_days,
            "broke_ma250_recently": broke_ma250_recently,
            "body": body,
            "lower_shadow": lower_shadow,
            "upper_shadow": upper_shadow,
        }

    # ------------------------------------------------------
    # 触发规则
    # ------------------------------------------------------
    def _check_signals(self, m: Dict) -> List[Dict]:
        """返回触发的信号列表 [{key,level,title,detail,action}]"""
        signals: List[Dict] = []

        c = m["close"]
        low = m["low"]
        vol = m["volume_bh"]
        vol_ma = m["vol_ma20_prev"] or 0
        ma250 = m["ma250"]
        pct = m["pct"]
        body = m["body"]
        low_shadow = m["lower_shadow"]

        # ① V 型收回
        if (V_LOW_BAND[0] <= low <= V_LOW_BAND[1]
                and c > KEY_LEVEL
                and pct > -1
                and vol > VOL_HUGE_BILLION
                and (not vol_ma or vol > vol_ma * 1.3)):
            signals.append({
                "key": "v_reversal",
                "level": 3,
                "title": "🚀 V 型收回（3 月剧本复刻）",
                "detail": (
                    f"日内低 {low:.2f} 触 3800 区 → 收盘 {c:.2f} 拉回，"
                    f"量 {vol:.0f}亿手（20日均 {vol_ma:.0f}）"
                ),
                "action": "建仓做多，可打 2-3 成仓，止损 3770",
            })

        # ② 放量长下影线（3800 ± 20）
        if (low <= LONG_HAMMER_LOW_MAX
                and body > 0
                and low_shadow > body * LONG_HAMMER_SHADOW_BODY_RATIO
                and vol > VOL_MEDIUM_BILLION):
            signals.append({
                "key": "hammer_at_3800",
                "level": 2,
                "title": "🔨 3800 区放量长下影",
                "detail": (
                    f"低 {low:.2f} 下影 {low_shadow:.1f} > 实体 {body:.1f} × 2，"
                    f"量 {vol:.0f}亿手"
                ),
                "action": "试探性建仓 1-2 成，止损 3770",
            })

        # ③ 站回 MA250 连续 3 日
        if ma250 and m["ma250_hold_days"] >= 3:
            signals.append({
                "key": f"ma250_hold_{m['ma250_hold_days']}",
                "level": 2,
                "title": "✅ 连续站上 MA250",
                "detail": (
                    f"已连续 {m['ma250_hold_days']} 日收盘 ≥ MA250 ({ma250:.2f})，"
                    f"当前 {c:.2f}"
                ),
                "action": "确认加仓信号，向 5 成靠拢，止损 MA250 下 2%",
            })

        # ④ MA250 反抽被拒
        if (ma250
                and m["broke_ma250_recently"]
                and abs(c - ma250) / ma250 <= MA250_REJECT_TOL
                and pct < -1
                and c < m["open"]):
            signals.append({
                "key": "ma250_reject",
                "level": 2,
                "title": "⚠️ MA250 反抽被拒",
                "detail": (
                    f"近 5 日曾破 MA250 ({ma250:.2f})，"
                    f"今日反抽至 {c:.2f} 收阴 {pct:.2f}%"
                ),
                "action": "减仓到 2 成，跌破反抽确认做空信号",
            })

        # ⑤ 缩量破位 3800
        if (c < KEY_LEVEL
                and vol_ma
                and vol < vol_ma * VOL_SHRINK_RATIO):
            signals.append({
                "key": "shrink_break_3800",
                "level": 2,
                "title": "🔻 缩量破位 3800",
                "detail": (
                    f"收 {c:.2f} < 3800，量 {vol:.0f}亿手 < 20日均 {vol_ma:.0f} × 0.8"
                ),
                "action": "空仓观望，下看 3600 缺口",
            })

        # ⑥ 逼近止损 3700
        if KEY_STOP <= c <= KEY_STOP + NEAR_STOP_BAND:
            signals.append({
                "key": "near_stop_3700",
                "level": 2,
                "title": "⚠️ 逼近止损 3700",
                "detail": f"收 {c:.2f}，距 3700 仅 {c - KEY_STOP:.0f} 点",
                "action": "半仓者严守 3700 止损，破位无条件出",
            })

        # ⑦ 已跌破止损 3700
        if c < KEY_STOP:
            signals.append({
                "key": "break_stop_3700",
                "level": 3,
                "title": "🚨 跌破止损 3700",
                "detail": f"收 {c:.2f} < 3700，已下破 3 月低点缺口下沿",
                "action": "半仓者无条件清仓，等磨底完成再看",
            })

        # ⑧ 放量破位 3800（2026-07-17 实盘盲区修复）
        prev_vol = m.get("prev_vol_bh") or 0
        vol_vs_ma = (vol > vol_ma * VOL_BREAK_RATIO) if vol_ma else False
        vol_vs_prev = (vol > prev_vol * VOL_BREAK_DAY_RATIO) if prev_vol else False
        if (c < KEY_LEVEL
                and (vol_vs_ma or vol_vs_prev)
                and pct < VOL_BREAK_PCT):
            vol_desc = (
                f"20日均 {vol_ma:.0f}×{VOL_BREAK_RATIO}" if vol_vs_ma
                else f"昨日 {prev_vol:.0f}×{VOL_BREAK_DAY_RATIO}"
            )
            signals.append({
                "key": "volume_break_3800",
                "level": 3,
                "title": "🚨 放量破位 3800（恐慌盘出货）",
                "detail": (
                    f"收 {c:.2f} < 3800，量 {vol:.0f}亿手 > {vol_desc}，"
                    f"跌幅 {pct:+.2f}%"
                ),
                "action": "不入场；筑底三段式第一段（放量破位→缩量阴跌→无量筑底），等 2-5 日缩量确认",
            })

        return signals

    # ------------------------------------------------------
    # 主流程
    # ------------------------------------------------------
    def run(self) -> bool:
        if not self.config.get("shanghai_watch.enabled", True):
            return True

        try:
            kline = self._fetch_kline()
        except Exception as e:
            self.log(f"K 线获取失败: {e}")
            return False

        m = self._build_metrics(kline)
        signals = self._check_signals(m)

        # 一日一推：同 key 已推过就跳过（force 除外）
        new_signals = []
        for s in signals:
            state_key = f"{s['key']}_{self.today}"
            if self.state.has(state_key) and not self.force:
                continue
            new_signals.append((state_key, s))

        # 无信号 → 静默或 snapshot 模式打印
        if not new_signals:
            if self.snapshot:
                self._print_snapshot(m)
            return True

        # 拼装推送
        lines = [
            f"【🐉 上证 3800 剧本触发】 {self.now_str}",
            f"────────────────────────────────",
            f"收盘 {m['close']:.2f}  {m['pct']:+.2f}%  "
            f"（低 {m['low']:.2f} / 高 {m['high']:.2f}）",
            f"量能 {m['volume_bh']:.0f} 亿手"
            + (f"  vs 20日均 {m['vol_ma20_prev']:.0f}" if m["vol_ma20_prev"] else ""),
            f"MA5 {m['ma5']:.0f} / MA20 {m['ma20']:.0f} / "
            f"MA60 {m['ma60']:.0f} / MA250 {m['ma250']:.0f}",
            "",
        ]
        max_level = 0
        for _, s in new_signals:
            lines.append(f"◆ {s['title']}  [level={s['level']}]")
            lines.append(f"   {s['detail']}")
            lines.append(f"   → {s['action']}")
            lines.append("")
            max_level = max(max_level, s["level"])

        lines.append("参考：notes/2026-07-16-shanghai-3800-entry-review.md")

        message = "\n".join(lines)
        meta = {
            "scenario": "shanghai_watch",
            "symbol": SH_SYMBOL,
            "max_level": max_level,
            "metrics": {
                "close": m["close"],
                "pct": m["pct"],
                "volume_bh": m["volume_bh"],
                "ma250": m["ma250"],
            },
        }
        ok = self.send(message, meta=meta)
        if ok:
            self._persist_watch_signals(m, [s for _, s in new_signals], push_log_id=self.last_push_log_id)
            for state_key, _ in new_signals:
                self.state.set(state_key)
        return ok

    def _persist_watch_signals(self, metrics: Dict, signals: List[Dict], push_log_id=None) -> None:
        """Persist each Shanghai-watch trigger as a first-class Signal."""
        rows = []
        for s in signals:
            signal_type, direction = self._signal_type_for_key(s["key"])
            rows.append(Signal(
                monitor=self.name,
                signal_type=signal_type,
                title=s["title"],
                symbol=SH_SYMBOL,
                symbols=[SH_SYMBOL],
                direction=direction,
                level=s["level"],
                summary=s["detail"],
                metrics={
                    "key": s["key"],
                    "detail": s["detail"],
                    "action": s["action"],
                    "close": metrics["close"],
                    "pct": metrics["pct"],
                    "low": metrics["low"],
                    "high": metrics["high"],
                    "volume_bh": metrics["volume_bh"],
                    "vol_ma20_prev": metrics["vol_ma20_prev"],
                    "ma250": metrics["ma250"],
                    "ma250_hold_days": metrics["ma250_hold_days"],
                    "trigger": s["key"],
                },
                dedup_key=f"{s['key']}_{self.today}",
                status="pushed",
                ts=self.now,
                push_log_id=push_log_id,
            ))

        if not rows:
            return
        try:
            from ..data import get_session
            with get_session() as session:
                persist_signals(session, rows)
        except Exception as e:
            self.log(f"结构化信号落库失败（不影响推送）: {e}")

    @staticmethod
    def _signal_type_for_key(key: str) -> tuple[str, int]:
        if key == "v_reversal":
            return "shanghai_v_reversal", 1
        if key == "hammer_at_3800":
            return "shanghai_hammer_at_3800", 1
        if key.startswith("ma250_hold_"):
            return "shanghai_ma250_hold", 1
        if key == "ma250_reject":
            return "shanghai_ma250_reject", -1
        if key == "shrink_break_3800":
            return "shanghai_shrink_break_3800", -1
        if key == "near_stop_3700":
            return "shanghai_near_stop_3700", -1
        if key == "break_stop_3700":
            return "shanghai_break_stop_3700", -1
        if key == "volume_break_3800":
            return "shanghai_volume_break_3800", -1
        return "shanghai_near_stop_3700", 0

    def _print_snapshot(self, m: Dict) -> None:
        print(f"[shanghai_watch] {self.now_str} 无触发信号")
        print(
            f"  close={m['close']:.2f} pct={m['pct']:+.2f}% "
            f"low={m['low']:.2f} vol={m['volume_bh']:.0f}亿手"
        )
        print(
            f"  MA5={m['ma5']:.0f} MA20={m['ma20']:.0f} "
            f"MA60={m['ma60']:.0f} MA250={m['ma250']:.0f}"
        )
        print(f"  MA250 已站上天数: {m['ma250_hold_days']}")
