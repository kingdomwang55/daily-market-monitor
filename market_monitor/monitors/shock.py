"""A 股异常波动预警"""
from ..core.base import BaseMonitor
from ..core import data_source as ds


class ShockMonitor(BaseMonitor):
    name = "shock"
    display_name = "A股异动"

    LEVEL_EMOJIS = ["📊", "⚠️", "🚨", "🚨🚨🚨"]

    def run(self) -> bool:
        cfg = self.config
        indices_cfg = cfg.get("shock.indices", [])
        thresholds = cfg.get("shock.thresholds", [1.5, 2.5, 3.5])
        sector_threshold = cfg.get("shock.sector_threshold", 4.0)

        codes = [x["code"] for x in indices_cfg]
        try:
            lines = ds.sina_realtime(codes)
        except Exception as e:
            self.log(f"数据获取失败: {e}")
            return False

        indices = []
        for i, cfg_item in enumerate(indices_cfg):
            if i < len(lines):
                info = ds.parse_index_simple(lines[i])
                if info:
                    indices.append((cfg_item["name"], info))

        if not indices:
            self.log("无指数数据")
            return False

        # 分级判定
        def level_of(pct: float) -> int:
            ap = abs(pct)
            if ap >= thresholds[2]:
                return 3
            if ap >= thresholds[1]:
                return 2
            if ap >= thresholds[0]:
                return 1
            return 0

        def level_emoji(level: int, pct: float) -> str:
            up = pct > 0
            if level == 3:
                return "🚀🚀🚀" if up else "🚨🚨🚨"
            if level == 2:
                return "📈📈" if up else "⚠️⚠️"
            if level == 1:
                return "📈" if up else "⚠️"
            return "⚪"

        index_alerts = []
        max_level = 0
        for name, info in indices:
            lvl = level_of(info["pct"])
            if lvl > 0:
                key = f"{name}_{self.today}_L{lvl}"
                if not self.state.has(key) or self.force:
                    index_alerts.append(
                        f"{level_emoji(lvl, info['pct'])} {name} "
                        f"{info['close']:.2f} {info['pct']:+.2f}%"
                    )
                    self.state.set(key)
                    max_level = max(max_level, lvl)

        # 板块异动（中级别以上才拉）
        sector_alerts = []
        if max_level >= 2 or self.force:
            sectors = ds.eastmoney_sectors()
            if sectors:
                sectors.sort(key=lambda x: x["pct"])
                for s in sectors[:5]:
                    if s["pct"] <= -sector_threshold:
                        key = f"sector_down_{s['name']}_{self.today}"
                        if not self.state.has(key):
                            sector_alerts.append(f"🔴 {s['name']} {s['pct']:+.2f}%")
                            self.state.set(key)
                for s in sectors[-5:][::-1]:
                    if s["pct"] >= sector_threshold:
                        key = f"sector_up_{s['name']}_{self.today}"
                        if not self.state.has(key):
                            sector_alerts.append(f"🟢 {s['name']} {s['pct']:+.2f}%")
                            self.state.set(key)

        if not (index_alerts or sector_alerts or self.force):
            self.log(f"{self.now_str} 大盘平稳")
            return True

        header = self.LEVEL_EMOJIS[min(max_level, 3)]
        parts = [f"{header} A 股异动预警 ({self.now_str})"]

        if index_alerts:
            parts.append("\n📉 大盘异动:")
            parts.extend(index_alerts)

        if sector_alerts:
            parts.append("\n🏭 板块异动:")
            parts.extend(sector_alerts)

        if max_level >= 3:
            parts.append("\n💡 严重异动：建议立即查看持仓，防御性资产（黄金/红利）优先")
        elif max_level >= 2:
            parts.append("\n💡 警戒级别：注意仓位控制，观察是否有持续性")
        elif max_level >= 1:
            parts.append("\n💡 轻度波动：关注但不必操作")

        message = "\n".join(parts)
        if self.send(message):
            self.log(f"✅ 已发送 {self.now_str}")
            self.state.save()
            return True
        self.log("❌ 发送失败")
        return False
