"""美股夜盘监控"""
from ..core.base import BaseMonitor
from ..core import data_source as ds
from ..core.teaching import us_teaching


class UsMarketMonitor(BaseMonitor):
    name = "us_market"
    display_name = "美股夜盘"

    def run(self) -> bool:
        cfg = self.config
        indices_cfg = cfg.get("us_market.indices", [])
        stocks_cfg = cfg.get("us_market.stocks", [])
        alert_index = cfg.get("us_market.alert_index_pct", 1.5)
        alert_stock = cfg.get("us_market.alert_stock_pct", 3.0)

        codes = [x["code"] for x in indices_cfg + stocks_cfg]
        try:
            lines = ds.sina_realtime(codes)
        except Exception as e:
            self.log(f"数据获取失败: {e}")
            return False

        indices, stocks = [], []
        for i, cfg_item in enumerate(indices_cfg):
            if i < len(lines):
                info = ds.parse_us_index(lines[i])
                if info:
                    indices.append((cfg_item["name"], info))

        for i, cfg_item in enumerate(stocks_cfg):
            idx = i + len(indices_cfg)
            if idx < len(lines):
                info = ds.parse_us_stock(lines[idx])
                if info:
                    stocks.append((cfg_item["name"], info))

        # 异动检查
        alerts = []
        stabilization_alerts = []
        for name, info in indices:
            if abs(info["pct"]) >= alert_index:
                key = f"alert_{name}_{self.today}_{int(info['pct']//1)}"
                if not self.state.has(key) or self.force:
                    alerts.append(f"{self.emoji_by_pct(info['pct'])} {name} "
                                  f"{info['close']:.2f} {info['pct']:+.2f}%")
                    self.state.set(key)
            
            # 止跌回稳信号检测：大跌后探底回升
            # 条件：日内跌幅 ≥ 1%，且从日内低点反弹幅度 ≥ 30%（(close - low)/(high - low) ≥ 0.3）
            if (info["pct"] <= -1.0 and "high" in info and "low" in info 
                and info["high"] > info["low"] and info["close"] > info["low"]):
                rebound_pct = (info["close"] - info["low"]) / (info["high"] - info["low"])
                if rebound_pct >= 0.3:
                    key = f"stabilize_{name}_{self.today}"
                    if not self.state.has(key) or self.force:
                        stabilization_alerts.append(
                            f"✳️ 止跌回稳: {name}\n"
                            f"  跌幅 {info['pct']:.2f}% | 低点 {info['low']:.2f} | 现价 {info['close']:.2f}\n"
                            f"  从低点反弹 {(rebound_pct*100):.0f}%，接近今日振幅中上部"
                        )
                        self.state.set(key)

        for name, info in stocks:
            if abs(info["pct"]) >= alert_stock:
                key = f"alert_{name}_{self.today}_{int(info['pct']//1)}"
                if not self.state.has(key) or self.force:
                    alerts.append(f"{self.emoji_by_pct(info['pct'])} {name} "
                                  f"${info['close']:.2f} {info['pct']:+.2f}%")
                    self.state.set(key)

        should_send = self.force or self.snapshot or alerts or stabilization_alerts
        if not should_send:
            self.log(f"{self.now_str} 美股平稳，未触发")
            return True

        parts = [f"🌍 美股监控 ({self.now_str})"]
        if alerts:
            parts.append("\n⚡ 【异动预警】")
            parts.extend(alerts)
        if stabilization_alerts:
            parts.append("\n✳️ 【止跌回稳信号】")
            parts.extend(stabilization_alerts)

        parts.append("\n📈 三大指数:")
        for name, info in indices:
            parts.append(f"{self.emoji_by_pct(info['pct'])} {name}: "
                         f"{info['close']:.2f} {info['pct']:+.2f}%")

        parts.append("\n💼 中概+科技:")
        for name, info in stocks:
            parts.append(f"{self.emoji_by_pct(info['pct'])} {name} "
                         f"${info['close']:.2f} {info['pct']:+.2f}%")

        parts.append(f"\n💡 阈值: 指数 ±{alert_index}% / 个股 ±{alert_stock}%")

        # 教学解读
        index_pcts = [info["pct"] for _, info in indices]
        parts.append("")
        parts.append(us_teaching(bool(alerts), index_pcts))

        message = "\n".join(parts)
        if self.send(message):
            self.log(f"✅ 已发送 {self.now_str}")
            self.state.save()
            return True
        self.log("❌ 发送失败")
        return False
