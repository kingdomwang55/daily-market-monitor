"""盘中脉搏观察（10:30 / 14:00 触发）
性格：条件优先 + 平淡日轻量心跳
- 有信号 → 详细推 + 建议动作
- 无信号 → 一行心跳（"HH:MM 上证 3990 +0.3% 无异动"）

触发条件（任一命中即为"有信号"）：
1. 主要指数涨跌 ≥ ±1%
2. 距离关键点位 ±1% 以内（预警"快到了"）
3. 出现企稳信号命中 ≥ 2 个
4. 板块异动（板块指数 ≥ ±2%）
5. 防御性资产异动（沪金/相关避险资产 ≥ ±1%）
"""
from ..core.base import BaseMonitor
from ..core import data_source as ds
from ..core.teaching import stabilize_teaching


class PulseMonitor(BaseMonitor):
    name = "pulse"
    display_name = "盘中脉搏"

    # ---------- 主要指数 ----------
    def _index_snapshot(self):
        """返回 [(name, code, price, pct)]，取自 stabilize.symbols 复用配置"""
        symbols = self.config.get("stabilize.symbols", [])
        if not symbols:
            return []
        codes = [s["code"] for s in symbols]
        try:
            lines = ds.sina_realtime(codes)
        except Exception as e:
            self.log(f"指数数据获取失败: {e}")
            return []
        result = []
        for i, s in enumerate(symbols):
            if i >= len(lines):
                continue
            info = ds.parse_stock(lines[i])
            if info:
                result.append({
                    "name": s["name"],
                    "code": s["code"],
                    "price": info["close"],
                    "pct": info["pct"],
                })
        return result

    # ---------- 关键点位距离 ----------
    def _key_level_proximity(self):
        """检查距关键点位是否 ≤1%，返回预警行列表"""
        targets = self.config.get("price_alert.targets", [])
        warnings = []
        for t in targets:
            code = t["code"]
            name = t["name"]
            stop = t.get("stop_loss")
            add = t.get("add_position")

            # 复用 price_alert 的取价逻辑（简化版）
            price = self._get_price(code, t.get("is_gold", False))
            if not price or price <= 0:
                continue

            if stop:
                gap = (price - stop) / stop * 100
                if 0 < gap <= 1.0:
                    warnings.append(
                        f"⚠️ {name} 逼近止损: {price:.2f} 距 {stop} 仅 {gap:+.2f}%"
                    )
            if add:
                gap = (add - price) / price * 100
                if 0 < gap <= 1.0:
                    warnings.append(
                        f"⚠️ {name} 逼近加仓: {price:.2f} 距 {add} 仅 {gap:+.2f}%"
                    )
        return warnings

    def _get_price(self, code: str, is_gold: bool = False) -> float:
        try:
            lines = ds.sina_realtime([code])
            if not lines:
                return 0
            line = lines[0]
            if code.startswith("s_"):
                info = ds.parse_index_simple(line)
                return info["close"] if info else 0
            if is_gold or code.startswith("nf_"):
                import re
                m = re.search(r'"([^"]+)"', line)
                if not m:
                    return 0
                parts = m.group(1).split(",")
                if len(parts) > 4:
                    try:
                        return float(parts[3]) or float(parts[8])
                    except (ValueError, IndexError):
                        return 0
                return 0
            info = ds.parse_stock(line)
            return info["close"] if info else 0
        except Exception:
            return 0

    # ---------- 企稳信号（复用 stabilize 逻辑） ----------
    def _stabilize_signals(self, symbol: str, min_sigs: int = 2):
        """返回 (name, signals_list) 当命中 ≥ min_sigs 时"""
        kline = ds.get_kline(symbol, days=10)
        if len(kline) < 3:
            return None
        latest, prev = kline[-1], kline[-2]
        lc = float(latest["close"])
        lo = float(latest["open"])
        ll = float(latest["low"])
        lv = float(latest["volume"])
        pc = float(prev["close"])
        po = float(prev["open"])
        pl = float(prev["low"])
        pv = float(prev["volume"])
        ma5 = sum(float(k["close"]) for k in kline[-5:]) / 5
        pct = (lc - pc) / pc * 100

        signals = []
        if ll >= pl * 0.995 and lc > pc * 0.99:
            signals.append(f"✅ 止跌确认：低点 {ll:.2f} ≥ 前日低 {pl:.2f}")
        if lc >= ma5:
            signals.append(f"✅ 均线修复：收 {lc:.2f} ≥ MA5 {ma5:.2f}")
        if lc > po and lc > lo:
            signals.append(f"✅ 阳线反包：收 {lc:.2f} > 前日开 {po:.2f}")
        if lv < pv * 0.9 and abs(pct) < abs((pc - po) / po * 100):
            signals.append(f"✅ 缩量止跌：{lv/1e8:.1f}亿 < 前日 {pv/1e8:.1f}亿")
        body = abs(lc - lo)
        lower = min(lc, lo) - ll
        if body > 0 and lower > body * 2 and lc > lo:
            signals.append(f"✅ 锤头形态：下影 {lower:.1f} > 实体 {body:.1f}×2")

        return signals if len(signals) >= min_sigs else None

    # ---------- 板块异动 ----------
    def _sector_shock(self, threshold: float = 2.0):
        """返回涨跌 ≥ threshold 的板块列表"""
        try:
            sectors = ds.eastmoney_sectors()
        except Exception as e:
            self.log(f"板块数据获取失败: {e}")
            return []
        if not sectors:
            return []
        result = []
        for s in sectors:
            pct = s.get("pct", 0)
            if abs(pct) >= threshold:
                result.append({
                    "name": s.get("name", "?"),
                    "pct": pct,
                    "price": s.get("price", 0),
                })
        # 按幅度绝对值排序，取前 5
        result.sort(key=lambda x: -abs(x["pct"]))
        return result[:5]

    # ---------- 防御性资产异动 ----------
    def _defensive_shock(self, threshold: float = 1.0):
        """返回涨跌 ≥ threshold 的防御性资产"""
        assets = self.config.get("defensive_assets", [])
        if not assets:
            return []
        codes = [a["code"] for a in assets]
        try:
            lines = ds.sina_realtime(codes)
        except Exception as e:
            self.log(f"防御性资产获取失败: {e}")
            return []
        result = []
        for i, a in enumerate(assets):
            if i >= len(lines):
                continue
            info = ds.parse_stock(lines[i])
            if info and abs(info["pct"]) >= threshold:
                result.append({
                    "name": a["name"],
                    "category": a["category"],
                    "price": info["close"],
                    "pct": info["pct"],
                })
        return result

    # ---------- 主流程 ----------
    def run(self) -> bool:
        # 采集所有数据
        indices = self._index_snapshot()
        if not indices:
            self.log("无指数数据，跳过")
            return True

        # 信号检测
        signals_hit = []  # 触发条件的原因列表（供日志）
        detail_parts = []  # 详细推送内容
        action_hints = []  # 建议动作

        # 1. 指数大幅波动 ≥ ±1%
        big_movers = [i for i in indices if abs(i["pct"]) >= 1.0]
        if big_movers:
            signals_hit.append(f"指数波动: {[i['name'] for i in big_movers]}")
            detail_parts.append("📊 【指数异动】")
            for i in big_movers:
                emoji = self.emoji_by_pct(i["pct"])
                detail_parts.append(f"{emoji} {i['name']}: {i['price']:.2f} {i['pct']:+.2f}%")
                if i["pct"] <= -1.5:
                    action_hints.append(f"⚠️ {i['name']} 跌 {i['pct']:.2f}%，关注止损位")
                elif i["pct"] >= 1.5:
                    action_hints.append(f"💡 {i['name']} 涨 {i['pct']:.2f}%，注意是否追高")

        # 2. 距关键点位 ≤1%
        proximity = self._key_level_proximity()
        if proximity:
            signals_hit.append(f"逼近点位: {len(proximity)}")
            detail_parts.append("")
            detail_parts.append("🎯 【关键点位预警】")
            detail_parts.extend(proximity)
            action_hints.append("💡 距离关键点位很近，做好挂单准备")

        # 3. 企稳信号
        stabilize_msg = []
        symbols_cfg = self.config.get("stabilize.symbols", [])
        for s in symbols_cfg:
            sigs = self._stabilize_signals(s["code"], min_sigs=2)
            if sigs:
                signals_hit.append(f"企稳: {s['name']}")
                if not stabilize_msg:
                    stabilize_msg.append("📈 【企稳信号】")
                stabilize_msg.append(f"\n{s['name']}:")
                stabilize_msg.extend(sigs)
        if stabilize_msg:
            detail_parts.append("")
            detail_parts.extend(stabilize_msg)
            action_hints.append("💡 企稳信号确认，可考虑分批介入")

        # 4. 板块异动
        sectors = self._sector_shock(threshold=2.0)
        if sectors:
            signals_hit.append(f"板块: {sectors[0]['name']}")
            detail_parts.append("")
            detail_parts.append("🔥 【板块异动】(±2%)")
            for s in sectors:
                emoji = self.emoji_by_pct(s["pct"])
                detail_parts.append(f"{emoji} {s['name']} {s['pct']:+.2f}%")

        # 5. 防御性资产异动
        defensive = self._defensive_shock(threshold=1.0)
        if defensive:
            signals_hit.append(f"避险: {[d['name'] for d in defensive]}")
            detail_parts.append("")
            detail_parts.append("🛡️ 【避险资产异动】")
            for d in defensive:
                emoji = self.emoji_by_pct(d["pct"])
                detail_parts.append(
                    f"{emoji} {d['name']}({d['category']}) "
                    f"{d['price']:.3f} {d['pct']:+.2f}%"
                )
            # 沪金/黄金拉升往往是避险情绪
            gold_up = [d for d in defensive if "金" in d["name"] and d["pct"] > 0]
            if gold_up:
                action_hints.append("💡 黄金资产走强，市场避险情绪升温")

        has_signal = bool(signals_hit)

        # ==== 组装消息 ====
        if has_signal:
            # 详细推送
            parts = [f"💓 盘中脉搏 · 有信号 ({self.now_str})"]
            parts.append("")
            # 先列出所有指数概况（1 行/个）
            parts.append("📍 大盘概览:")
            for i in indices:
                emoji = self.emoji_by_pct(i["pct"])
                parts.append(f"  {emoji} {i['name']}: {i['price']:.2f} {i['pct']:+.2f}%")
            # 详细信号
            parts.extend(detail_parts)
            # 建议动作
            if action_hints:
                parts.append("")
                parts.append("🎬 建议关注:")
                for h in action_hints:
                    parts.append(f"  {h}")
            # 教学（如果有企稳）
            if stabilize_msg:
                triggered_all = []
                for s in symbols_cfg:
                    sigs = self._stabilize_signals(s["code"], min_sigs=2)
                    if sigs:
                        triggered_all.extend(sigs)
                if triggered_all:
                    parts.append("")
                    parts.append(stabilize_teaching(triggered_all))
        else:
            # 一行心跳
            heartbeat_bits = []
            for i in indices:
                emoji = self.emoji_by_pct(i["pct"])
                heartbeat_bits.append(
                    f"{emoji}{i['name']} {i['price']:.0f} {i['pct']:+.2f}%"
                )
            parts = [
                f"💓 {self.now_str} 无异动 | " + " · ".join(heartbeat_bits)
            ]

        message = "\n".join(parts)

        # ─── 落库 meta ───
        if has_signal:
            # 信号分类：按优先级取一个主要 signal_type
            if big_movers:
                idx_avg = sum(i["pct"] for i in big_movers) / len(big_movers)
                signal_type = "pulse_index_up" if idx_avg > 0 else "pulse_index_down"
            elif proximity:
                signal_type = "pulse_near_key_level"
            elif stabilize_msg:
                signal_type = "pulse_stabilize"
            elif sectors:
                signal_type = "pulse_sector_move"
            elif defensive:
                signal_type = "pulse_defensive"
            else:
                signal_type = "pulse_other"
            max_level = 2
        else:
            signal_type = "pulse_heartbeat"
            max_level = 0

        idx_avg_all = (
            sum(i["pct"] for i in indices) / len(indices)
            if indices else 0.0
        )
        meta = {
            "scenario": signal_type,
            "max_level": max_level,
            "signal_type": signal_type,
            "a_avg_pct": round(idx_avg_all, 3),
            "signals_hit": signals_hit,
            "has_signal": has_signal,
            "metrics": {
                "indices": indices,
                "proximity_count": len(proximity),
                "stabilize_hits": len(stabilize_msg),
                "sector_count": len(sectors),
                "defensive_count": len(defensive),
            },
        }
        if self.send(message, meta=meta):
            status = "有信号" if has_signal else "心跳"
            self.log(f"✅ {status} 已发送 {self.now_str} type={signal_type} | 触发: {signals_hit}")
            self.state.save()
            return True
        self.log("❌ 发送失败")
        return False
