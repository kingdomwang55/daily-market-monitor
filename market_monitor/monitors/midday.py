"""午间盘中综述监控（12:15 触发）
合并 A 股企稳信号 + 港股半日行情 + 南下资金 + 防御性资产为一条综合推送。
替代原来每天 22 次的 stabilize + hk_market 定时轮询。
"""
from ..core.base import BaseMonitor
from ..core import data_source as ds
from ..core.teaching import stabilize_teaching, hk_teaching, southbound_teaching


class MiddayMonitor(BaseMonitor):
    name = "midday"
    display_name = "午间综述"

    # ---------- A 股企稳信号（精简自 StabilizeMonitor） ----------
    def _check_stabilize(self, symbol: str):
        kline = ds.get_kline(symbol, days=10)
        if len(kline) < 3:
            return None, []

        latest, prev = kline[-1], kline[-2]
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
        if latest_low >= prev_low * 0.995 and latest_close > prev_close * 0.99:
            signals.append(f"✅ 止跌确认：低点 {latest_low:.2f} ≥ 前日低点 {prev_low:.2f}")
        if latest_close >= ma5:
            signals.append(f"✅ 均线修复：收 {latest_close:.2f} ≥ MA5 {ma5:.2f}")
        if latest_close > prev_open and latest_close > latest_open:
            signals.append(f"✅ 阳线反包：收 {latest_close:.2f} > 前日开 {prev_open:.2f}")
        if latest_vol < prev_vol * 0.9 and abs(pct) < abs((prev_close - prev_open) / prev_open * 100):
            signals.append(f"✅ 缩量止跌：量能 {latest_vol/1e8:.1f}亿 < 前日 {prev_vol/1e8:.1f}亿")
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
        }
        return info, signals

    def _defensive_snapshot(self):
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

    # ---------- 港股数据（精简自 HkMarketMonitor） ----------
    def _hk_snapshot(self):
        cfg = self.config
        indices_cfg = cfg.get("hk_market.indices", [])
        stocks_cfg = cfg.get("hk_market.stocks", [])
        codes = [x["code"] for x in indices_cfg + stocks_cfg]
        if not codes:
            return [], []
        try:
            lines = ds.sina_realtime(codes)
        except Exception as e:
            self.log(f"港股数据获取失败: {e}")
            return [], []

        indices, stocks = [], []
        for i, cfg_item in enumerate(indices_cfg):
            if i < len(lines):
                info = ds.parse_hk_index(lines[i])
                if info:
                    indices.append((cfg_item["name"], info))
        for i, cfg_item in enumerate(stocks_cfg):
            idx = i + len(indices_cfg)
            if idx < len(lines):
                info = ds.parse_hk_stock(lines[idx])
                if info:
                    stocks.append((cfg_item["name"], info))
        return indices, stocks

    # ---------- 主流程 ----------
    def run(self) -> bool:
        parts = [f"☀️ 午间盘中综述 ({self.now_str})"]

        # ===== 1. A 股企稳信号 =====
        symbols = self.config.get("stabilize.symbols", [])
        min_signals = self.config.get("stabilize.min_signals", 2)
        stabilize_lines = []
        triggered = []
        watch_lines = []
        for s in symbols:
            info, signals = self._check_stabilize(s["code"])
            if not info:
                continue
            if len(signals) >= min_signals:
                stabilize_lines.append(f"\n📈 【{s['name']} 企稳信号】")
                stabilize_lines.append(
                    f"收 {info['close']:.2f} ({info['pct']:+.2f}%)  MA5 {info['ma5']:.2f}"
                )
                stabilize_lines.extend(signals)
                triggered.extend(signals)
            else:
                watch_lines.append(
                    f"  {s['name']}: {info['close']:.2f} ({info['pct']:+.2f}%) "
                    f"命中 {len(signals)}/5"
                )

        if stabilize_lines:
            parts.append("\n【A 股企稳】")
            parts.extend(stabilize_lines)
        elif watch_lines:
            parts.append("\n⏳ 【A 股企稳观察】")
            parts.extend(watch_lines)

        # ===== 2. 港股半日 =====
        indices, stocks = self._hk_snapshot()
        if indices or stocks:
            parts.append("\n🇭🇰 【港股半日】")
            for name, info in indices:
                parts.append(
                    f"{self.emoji_by_pct(info['pct'])} {name}: "
                    f"{info['close']:.2f} {info['pct']:+.2f}%"
                )
            if stocks:
                parts.append("")
                parts.append("💼 港股通热门:")
                for name, info in stocks:
                    parts.append(
                        f"{self.emoji_by_pct(info['pct'])} {name} "
                        f"HK${info['close']:.2f} {info['pct']:+.2f}%"
                    )

        # ===== 3. 南下资金 =====
        try:
            south_latest = ds.fetch_south_flow_latest()
            south_trend = ds.fetch_south_flow_trend(days=5)
            if south_latest:
                net = south_latest.get("net")
                if net is not None:
                    arrow = "🟢" if net >= 0 else "🔴"
                    direction = "流入" if net >= 0 else "流出"
                    parts.append(
                        f"\n💰 南下资金（{south_latest.get('date','')}）"
                        f" {arrow} 净{direction} {net:+.2f} 亿"
                    )
                south_teach = southbound_teaching(south_latest, south_trend)
                if south_teach:
                    parts.append(south_teach)
        except Exception as e:
            self.log(f"南下资金数据获取失败: {e}")

        # ===== 4. 防御性资产（每日首次） =====
        daily_key = f"midday_defensive_{self.today}"
        if self.force or not self.state.has(daily_key):
            assets = self._defensive_snapshot()
            if assets:
                parts.append("\n🛡️ 【防御性资产】")
                categories = {}
                for a in assets:
                    categories.setdefault(a["category"], []).append(a)
                for cat, items in categories.items():
                    for a in items:
                        parts.append(
                            f"{a['emoji']} {a['name']} ({a['code'][2:]}) "
                            f"{a['price']:.3f} {a['pct']:+.2f}%"
                        )
                self.state.set(daily_key)

        # ===== 5. 教学解读 =====
        if triggered:
            parts.append("")
            parts.append(stabilize_teaching(triggered))
        if indices:
            parts.append("")
            parts.append(hk_teaching(False, [i["pct"] for _, i in indices]))

        message = "\n".join(parts)
        if self.send(message):
            self.log(f"✅ 已发送 {self.now_str}")
            self.state.save()
            return True
        self.log("❌ 发送失败")
        return False
