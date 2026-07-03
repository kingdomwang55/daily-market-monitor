"""港股监控"""
from ..core.base import BaseMonitor
from ..core import data_source as ds


class HkMarketMonitor(BaseMonitor):
    name = "hk_market"
    display_name = "港股监控"

    def run(self) -> bool:
        cfg = self.config
        indices_cfg = cfg.get("hk_market.indices", [])
        stocks_cfg = cfg.get("hk_market.stocks", [])
        alert_index = cfg.get("hk_market.alert_index_pct", 1.5)
        alert_stock = cfg.get("hk_market.alert_stock_pct", 3.0)

        codes = [x["code"] for x in indices_cfg + stocks_cfg]
        try:
            lines = ds.sina_realtime(codes)
        except Exception as e:
            self.log(f"数据获取失败: {e}")
            return False

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

        alerts = []
        for name, info in indices:
            if abs(info["pct"]) >= alert_index:
                key = f"{name}_{self.today}_{int(info['pct']//1)}"
                if not self.state.has(key) or self.force:
                    alerts.append(f"{self.emoji_by_pct(info['pct'])} {name} "
                                  f"{info['close']:.2f} {info['pct']:+.2f}%")
                    self.state.set(key)

        for name, info in stocks:
            if abs(info["pct"]) >= alert_stock:
                key = f"{name}_{self.today}_{int(info['pct']//1)}"
                if not self.state.has(key) or self.force:
                    alerts.append(f"{self.emoji_by_pct(info['pct'])} {name} "
                                  f"{info['close']:.2f} {info['pct']:+.2f}%")
                    self.state.set(key)

        should_send = self.force or self.snapshot or alerts
        if not should_send:
            self.log(f"{self.now_str} 港股平稳，未触发")
            return True

        parts = [f"🇭🇰 港股监控 ({self.now_str})"]

        if alerts:
            parts.append("\n⚡ 【异动预警】")
            parts.extend(alerts)

        parts.append("\n📈 指数:")
        for name, info in indices:
            parts.append(f"{self.emoji_by_pct(info['pct'])} {name}: "
                         f"{info['close']:.2f} {info['pct']:+.2f}%")

        parts.append("\n💼 港股通热门:")
        for name, info in stocks:
            parts.append(f"{self.emoji_by_pct(info['pct'])} {name} "
                         f"HK${info['close']:.2f} {info['pct']:+.2f}%")

        parts.append(f"\n💡 A股先行指标 | 阈值: 指数 ±{alert_index}% / 个股 ±{alert_stock}%")

        message = "\n".join(parts)
        if self.send(message):
            self.log(f"✅ 已发送 {self.now_str}")
            self.state.save()
            return True
        self.log("❌ 发送失败")
        return False
