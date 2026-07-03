"""A 股企稳信号监控 + 防御性资产快照"""
from ..core.base import BaseMonitor
from ..core import data_source as ds


class StabilizeMonitor(BaseMonitor):
    name = "stabilize"
    display_name = "企稳信号"

    def _check_signals(self, symbol: str):
        """返回 (info, signals)"""
        kline = ds.get_kline(symbol, days=10)
        if len(kline) < 3:
            return None, []

        latest = kline[-1]
        prev = kline[-2]

        latest_close = float(latest["close"])
        latest_open = float(latest["open"])
        latest_low = float(latest["low"])
        latest_vol = float(latest["volume"])
        prev_close = float(prev["close"])
        prev_open = float(prev["open"])
        prev_low = float(prev["low"])
        prev_vol = float(prev["volume"])

        closes = [float(k["close"]) for k in kline[-5:]]
        ma5 = sum(closes) / len(closes)
        pct = (latest_close - prev_close) / prev_close * 100

        signals = []

        # 1. 止跌确认
        if latest_low >= prev_low * 0.995 and latest_close > prev_close * 0.99:
            signals.append(f"✅ 止跌确认：低点 {latest_low:.2f} ≥ 前日低点 {prev_low:.2f}")

        # 2. 均线修复
        if latest_close >= ma5:
            signals.append(f"✅ 均线修复：收 {latest_close:.2f} ≥ MA5 {ma5:.2f}")

        # 3. 反包/阳线
        if latest_close > prev_open and latest_close > latest_open:
            signals.append(f"✅ 阳线反包：收 {latest_close:.2f} > 前日开 {prev_open:.2f}")

        # 4. 缩量止跌
        if latest_vol < prev_vol * 0.9 and abs(pct) < abs((prev_close - prev_open) / prev_open * 100):
            signals.append(f"✅ 缩量止跌：量能 {latest_vol/1e8:.1f}亿 < 前日 {prev_vol/1e8:.1f}亿")

        # 5. 锤头线
        body = abs(latest_close - latest_open)
        lower_shadow = min(latest_close, latest_open) - latest_low
        if body > 0 and lower_shadow > body * 2 and latest_close > latest_open:
            signals.append(f"✅ 锤头形态：下影 {lower_shadow:.1f} > 实体 {body:.1f} × 2")

        info = {
            "symbol": symbol,
            "date": latest["day"],
            "close": latest_close,
            "pct": pct,
            "ma5": ma5,
            "prev_low": prev_low,
        }
        return info, signals

    def _get_defensive_snapshot(self):
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
            if i < len(lines):
                info = ds.parse_stock(lines[i])
                if info:
                    result.append({
                        "code": a["code"],
                        "name": a["name"],
                        "category": a["category"],
                        "price": info["close"],
                        "pct": info["pct"],
                        "emoji": self.emoji_by_pct(info["pct"]),
                    })
        return result

    def run(self) -> bool:
        symbols = self.config.get("stabilize.symbols", [])
        min_signals = self.config.get("stabilize.min_signals", 2)
        include_defensive = self.config.get("stabilize.include_defensive", True)

        signals_all = []
        for s in symbols:
            info, signals = self._check_signals(s["code"])
            if info:
                signals_all.append((s["name"], info, signals))

        # 是否有企稳
        push_stabilize = False
        stabilize_msg = ""
        for sym_name, info, signals in signals_all:
            key = f"stabilize_{info['symbol']}_{info['date']}"
            if len(signals) >= min_signals and not self.state.has(key):
                push_stabilize = True
                stabilize_msg += f"\n📈 【{sym_name} 企稳信号】\n"
                stabilize_msg += f"日期: {info['date']}  收盘: {info['close']:.2f}  涨跌: {info['pct']:+.2f}%\n"
                stabilize_msg += f"MA5: {info['ma5']:.2f}\n"
                stabilize_msg += "命中信号:\n" + "\n".join(signals) + "\n"
                self.state.set(key)

        # 每日首次防御快照
        daily_key = f"defensive_snapshot_{self.today}"
        push_defensive = include_defensive and (self.force or not self.state.has(daily_key))

        defensive_msg = ""
        if push_defensive:
            assets = self._get_defensive_snapshot()
            if assets:
                defensive_msg = "\n🛡️ 【防御性资产快照】\n"
                categories = {}
                for a in assets:
                    categories.setdefault(a["category"], []).append(a)
                for cat, items in categories.items():
                    for a in items:
                        defensive_msg += (
                            f"{a['emoji']} {a['name']} ({a['code'][2:]}) "
                            f"{a['price']:.3f} {a['pct']:+.2f}%\n"
                        )
                alloc = self.config.get("defensive_allocation", {})
                if alloc:
                    defensive_msg += "\n💡 建议配置:\n  " + " + ".join(
                        f"{k} {v}%" for k, v in alloc.items()
                    )
                    defensive_msg += "\n"
                self.state.set(daily_key)

        # 组装消息
        if push_stabilize or (push_defensive and defensive_msg) or self.force:
            parts = [f"🔔 市场信号 ({self.now_str})"]
            if stabilize_msg:
                parts.append(stabilize_msg)
            else:
                watch_msg = "\n⏳ 【企稳观察中】\n"
                for sym_name, info, signals in signals_all:
                    watch_msg += f"\n{sym_name}: {info['close']:.2f} ({info['pct']:+.2f}%)"
                    if signals:
                        watch_msg += f"  已命中 {len(signals)}/5 信号"
                    else:
                        watch_msg += "  尚未出现信号"
                parts.append(watch_msg)
            if defensive_msg:
                parts.append(defensive_msg)

            message = "\n".join(parts)
            if self.send(message):
                self.log(f"✅ 已发送 {self.now_str}")
                self.state.save()
                return True
            self.log("❌ 发送失败")
            return False
        else:
            self.log(f"{self.now_str} 静默：企稳信号未触发")
            for sym_name, info, signals in signals_all:
                self.log(
                    f"  {sym_name}: 收 {info['close']:.2f} ({info['pct']:+.2f}%) "
                    f"命中 {len(signals)}/5"
                )
            self.state.save()
            return True
