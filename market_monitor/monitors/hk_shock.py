"""港股异动预警（含 A 股联动）

设计要点：
- 分级：L1/L2/L3，恒指/恒科/个股各自阈值（波动特性不同）
- 联动：每次触发时同步拉一次 A 股实时数据（无缓存，确保准确）
- 时段：识别 A 股 live/closed/pre-market，给出不同联动叙事
- 去重：state 只做"本条告警发过没"，联动分析每次实时计算
"""
from datetime import time as dt_time
from ..core.base import BaseMonitor
from ..core import data_source as ds
from ..core.teaching import hk_shock_teaching
from ..signals import Signal
from ..signals.persist import persist_signals


class HkShockMonitor(BaseMonitor):
    name = "hk_shock"
    display_name = "港股异动"

    LEVEL_EMOJIS = ["📊", "⚠️", "🚨", "🚨🚨🚨"]

    # A 股交易时段（Asia/Shanghai 已是 self.now 的时区）
    A_MORNING_START = dt_time(9, 30)
    A_MORNING_END = dt_time(11, 30)
    A_AFTERNOON_START = dt_time(13, 0)
    A_AFTERNOON_END = dt_time(15, 0)

    def _a_share_stage(self) -> str:
        """判定当前 A 股状态：live / lunch / closed / pre"""
        t = self.now.time()
        wd = self.now.weekday()  # 0=Mon
        if wd >= 5:  # 周末
            return "closed"
        if t < self.A_MORNING_START:
            return "pre"
        if self.A_MORNING_START <= t <= self.A_MORNING_END:
            return "live"
        if self.A_MORNING_END < t < self.A_AFTERNOON_START:
            return "lunch"  # 午休，sina 数据是上午收盘价
        if self.A_AFTERNOON_START <= t <= self.A_AFTERNOON_END:
            return "live"
        return "closed"

    @staticmethod
    def _level_of(pct: float, thresholds) -> int:
        ap = abs(pct)
        if ap >= thresholds[2]:
            return 3
        if ap >= thresholds[1]:
            return 2
        if ap >= thresholds[0]:
            return 1
        return 0

    @staticmethod
    def _level_emoji(level: int, pct: float) -> str:
        up = pct > 0
        if level == 3:
            return "🚀🚀🚀" if up else "🚨🚨🚨"
        if level == 2:
            return "📈📈" if up else "⚠️⚠️"
        if level == 1:
            return "📈" if up else "⚠️"
        return "⚪"

    def _fetch_a_share_ref(self, ref_cfg):
        """同步拉取 A 股参考数据"""
        codes = [x["code"] for x in ref_cfg]
        try:
            lines = ds.sina_realtime(codes)
        except Exception as e:
            self.log(f"A 股参考数据拉取失败: {e}")
            return []
        result = []
        for i, item in enumerate(ref_cfg):
            if i < len(lines):
                info = ds.parse_index_simple(lines[i])
                if info:
                    result.append((item["code"], item["name"], info))
        return result

    def _classify_linkage(self, hk_avg: float, a_avg: float,
                          a_stage: str, diverge_th: float) -> str:
        """判定联动场景"""
        if a_stage == "closed":
            return "a_closed"
        if a_stage == "pre":
            return "a_not_open"

        # A 股在交易或午休：a_avg 有效
        hk_alerted = abs(hk_avg) >= diverge_th
        a_alerted = abs(a_avg) >= diverge_th

        # 反向 → 分歧
        if hk_avg * a_avg < 0 and (hk_alerted or a_alerted):
            return "divergence"

        # 港股异动 + A 股平稳
        if hk_alerted and not a_alerted:
            return "hk_only_down" if hk_avg < 0 else "hk_only_up"

        # 两边都异动 + 同向 → 共振
        if hk_alerted and a_alerted and hk_avg * a_avg > 0:
            return "resonance_down" if hk_avg < 0 else "resonance_up"

        return "neutral"

    def run(self) -> bool:
        cfg = self.config
        indices_cfg = cfg.get("hk_shock.indices", [])
        stocks_cfg = cfg.get("hk_shock.stocks", [])
        a_ref_cfg = cfg.get("hk_shock.a_share_ref", [])
        th_index = cfg.get("hk_shock.thresholds_index", [1.5, 2.5, 3.5])
        th_tech = cfg.get("hk_shock.thresholds_tech", [2.0, 3.5, 5.0])
        th_stock = cfg.get("hk_shock.thresholds_stock", [3.0, 5.0, 7.0])
        diverge_th = cfg.get("hk_shock.a_share_diverge_threshold", 1.0)

        # ─── 1. 拉港股数据 ───
        codes = [x["code"] for x in indices_cfg + stocks_cfg]
        try:
            lines = ds.sina_realtime(codes)
        except Exception as e:
            self.log(f"港股数据获取失败: {e}")
            return False

        indices = []
        for i, item in enumerate(indices_cfg):
            if i < len(lines):
                info = ds.parse_hk_index(lines[i])
                if info:
                    indices.append((item["code"], item["name"], item.get("type", "broad"), info))

        stocks = []
        for i, item in enumerate(stocks_cfg):
            idx = i + len(indices_cfg)
            if idx < len(lines):
                info = ds.parse_hk_stock(lines[idx])
                if info:
                    stocks.append((item["code"], item["name"], info))

        if not indices:
            self.log("无港股指数数据")
            return False

        # ─── 2. 分级判定 ───
        index_alerts = []
        index_breaks = []
        max_level = 0
        for code, name, itype, info in indices:
            th = th_tech if itype == "tech" else th_index
            lvl = self._level_of(info["pct"], th)
            if lvl > 0:
                key = f"{name}_{self.today}_L{lvl}"
                if not self.state.has(key) or self.force:
                    index_alerts.append(
                        f"{self._level_emoji(lvl, info['pct'])} {name} "
                        f"{info['close']:.2f} {info['pct']:+.2f}%"
                    )
                    index_breaks.append({
                        "code": code,
                        "name": name,
                        "type": itype,
                        "level": lvl,
                        "pct": info["pct"],
                        "close": info["close"],
                        "direction": "up" if info["pct"] > 0 else "down",
                    })
                    self.state.set(key)
                    max_level = max(max_level, lvl)

        stock_alerts = []
        stock_breaks = []
        for code, name, info in stocks:
            lvl = self._level_of(info["pct"], th_stock)
            if lvl > 0:
                key = f"stock_{name}_{self.today}_L{lvl}"
                if not self.state.has(key) or self.force:
                    stock_alerts.append(
                        f"{self._level_emoji(lvl, info['pct'])} {name} "
                        f"HK${info['close']:.2f} {info['pct']:+.2f}%"
                    )
                    stock_breaks.append({
                        "code": code,
                        "name": name,
                        "level": lvl,
                        "pct": info["pct"],
                        "close": info["close"],
                        "direction": "up" if info["pct"] > 0 else "down",
                    })
                    self.state.set(key)
                    max_level = max(max_level, lvl)

        if not (index_alerts or stock_alerts or self.force):
            self.log(f"{self.now_str} 港股平稳")
            return True

        # ─── 3. 实时拉 A 股参考（联动分析核心） ───
        a_stage = self._a_share_stage()
        a_ref = self._fetch_a_share_ref(a_ref_cfg) if a_ref_cfg else []

        hk_avg = (
            sum(info["pct"] for _, _, _, info in indices) / len(indices)
            if indices else 0
        )
        a_avg = (
            sum(info["pct"] for _, _, info in a_ref) / len(a_ref)
            if a_ref else 0
        )

        scenario = self._classify_linkage(hk_avg, a_avg, a_stage, diverge_th)
        linkage = {
            "scenario": scenario,
            "hk_avg_pct": hk_avg,
            "a_avg_pct": a_avg,
            "a_stage": a_stage,
        }

        # ─── 4. 拼装消息 ───
        header = self.LEVEL_EMOJIS[min(max_level, 3)]
        parts = [f"{header} 港股异动预警 ({self.now_str})"]

        # 告警区（仅列触发项）
        if index_alerts:
            parts.append("\n⚡ 指数异动:")
            parts.extend(index_alerts)

        if stock_alerts:
            parts.append("\n⚡ 个股异动:")
            parts.extend(stock_alerts)

        # 港股全景状态（所有指数 + 所有港股通标的，无论是否异动）
        parts.append("\n🇭🇰 港股指数:")
        for _, name, itype, info in indices:
            tag = " (科技)" if itype == "tech" else ""
            parts.append(
                f"{self.emoji_by_pct(info['pct'])} {name}{tag}: "
                f"{info['close']:.2f} {info['pct']:+.2f}%"
            )

        if stocks:
            parts.append("\n💼 港股通热门:")
            for _, name, info in stocks:
                parts.append(
                    f"{self.emoji_by_pct(info['pct'])} {name} "
                    f"HK${info['close']:.2f} {info['pct']:+.2f}%"
                )

        # A 股参考现状
        if a_ref:
            stage_label = {
                "live": "🟢 交易中",
                "lunch": "🍱 午休中(上午收盘价)",
                "closed": "🔒 已收盘",
                "pre": "🕐 未开盘",
            }.get(a_stage, "")
            parts.append(f"\n📊 A 股参考 [{stage_label}]:")
            for _, name, info in a_ref:
                parts.append(
                    f"{self.emoji_by_pct(info['pct'])} {name}: "
                    f"{info['close']:.2f} {info['pct']:+.2f}%"
                )

        # 快速操作建议（基于 max_level + scenario）
        if max_level >= 3:
            parts.append("\n💡 严重异动：港股 T+0，日内可先减仓避险；防御性资产优先")
        elif max_level >= 2:
            parts.append("\n💡 警戒级别：注意仓位控制，看下半场是否延续")
        elif max_level >= 1:
            parts.append("\n💡 轻度波动：观察为主")

        # 教学解读（含联动）
        parts.append("")
        parts.append(hk_shock_teaching(max_level, bool(stock_alerts), linkage))

        message = "\n".join(parts)
        # 递交 meta 给 base.send()，自动落库
        meta = {
            "scenario": scenario,
            "max_level": max_level,
            "hk_avg_pct": round(hk_avg, 3),
            "a_avg_pct": round(a_avg, 3),
            "a_stage": a_stage,
            "index_alerts_count": len(index_alerts),
            "stock_alerts_count": len(stock_alerts),
            "metrics": {
                "hk_indices": [
                    {"code": c, "name": n, "pct": info["pct"], "close": info["close"], "type": t}
                    for c, n, t, info in indices
                ],
                "hk_stocks": [
                    {"code": c, "name": n, "pct": info["pct"], "close": info["close"]}
                    for c, n, info in stocks
                ],
                "a_ref": [
                    {"code": c, "name": n, "pct": info["pct"], "close": info["close"]}
                    for c, n, info in a_ref
                ],
                "index_breaks": index_breaks,
                "stock_breaks": stock_breaks,
            },
        }
        if self.send(message, meta=meta):
            self._persist_hk_signals(
                scenario=scenario,
                hk_avg=hk_avg,
                a_avg=a_avg,
                a_stage=a_stage,
                index_breaks=index_breaks,
                stock_breaks=stock_breaks,
                push_log_id=self.last_push_log_id,
            )
            self.log(f"✅ 已发送 {self.now_str} scenario={scenario}")
            self.state.save()
            return True
        self.log("❌ 发送失败")
        return False

    def _persist_hk_signals(
        self,
        *,
        scenario: str,
        hk_avg: float,
        a_avg: float,
        a_stage: str,
        index_breaks: list[dict],
        stock_breaks: list[dict],
        push_log_id=None,
    ) -> None:
        """Persist each HK alert with the cross-market scenario attached."""
        signal_type = f"hk_{scenario}"
        scenario_direction = 1 if hk_avg > 0 else (-1 if hk_avg < 0 else 0)
        signals = []

        for item in index_breaks:
            item_direction = 1 if item["direction"] == "up" else -1
            signals.append(Signal(
                monitor=self.name,
                signal_type=signal_type,
                title=f"{item['name']} 港股指数异动",
                symbol=item["code"],
                symbols=[item["code"]],
                direction=item_direction or scenario_direction,
                level=item["level"],
                metrics={
                    "name": item["name"],
                    "type": item["type"],
                    "pct": item["pct"],
                    "close": item["close"],
                    "trigger": "hk_index_move",
                    "scenario": scenario,
                    "hk_avg_pct": round(hk_avg, 3),
                    "a_avg_pct": round(a_avg, 3),
                    "a_stage": a_stage,
                },
                dedup_key=f"{item['name']}_{self.today}_L{item['level']}",
                status="pushed",
                ts=self.now,
                push_log_id=push_log_id,
            ))

        for item in stock_breaks:
            item_direction = 1 if item["direction"] == "up" else -1
            signals.append(Signal(
                monitor=self.name,
                signal_type=signal_type,
                title=f"{item['name']} 港股个股异动",
                symbol=item["code"],
                symbols=[item["code"]],
                direction=item_direction or scenario_direction,
                level=item["level"],
                metrics={
                    "name": item["name"],
                    "pct": item["pct"],
                    "close": item["close"],
                    "trigger": "hk_stock_move",
                    "scenario": scenario,
                    "hk_avg_pct": round(hk_avg, 3),
                    "a_avg_pct": round(a_avg, 3),
                    "a_stage": a_stage,
                },
                dedup_key=f"stock_{item['name']}_{self.today}_L{item['level']}",
                status="pushed",
                ts=self.now,
                push_log_id=push_log_id,
            ))

        if not signals:
            return
        try:
            from ..data import get_session
            with get_session() as s:
                persist_signals(s, signals)
        except Exception as e:
            self.log(f"结构化信号落库失败（不影响推送）: {e}")
