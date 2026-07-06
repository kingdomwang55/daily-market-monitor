"""关键点位监控（止损/加仓位）"""
from ..core.base import BaseMonitor
from ..core import data_source as ds
from ..core.teaching import price_alert_teaching


class PriceAlertMonitor(BaseMonitor):
    name = "price_alert"
    display_name = "关键点位"

    def _get_price(self, code: str, is_gold: bool = False) -> float:
        """获取实时价格"""
        try:
            lines = ds.sina_realtime([code])
            if not lines:
                return 0
            line = lines[0]
            if code.startswith("s_"):
                info = ds.parse_index_simple(line)
            elif is_gold or code.startswith("nf_"):
                # 沪金格式特殊，用简单解析
                import re
                m = re.search(r'"([^"]+)"', line)
                if not m:
                    return 0
                parts = m.group(1).split(",")
                # nf_AU0 格式: 时间,开,高,低,现价,昨结,...
                if len(parts) > 4:
                    try:
                        return float(parts[3]) or float(parts[8])
                    except (ValueError, IndexError):
                        return 0
                return 0
            else:
                info = ds.parse_stock(line)
            return info["close"] if info else 0
        except Exception as e:
            self.log(f"取价失败 {code}: {e}")
            return 0

    def run(self) -> bool:
        targets = self.config.get("price_alert.targets", [])
        if not targets:
            return True

        alerts = []
        teachings = []  # 触发时附上的教学解读
        for t in targets:
            code = t["code"]
            name = t["name"]
            price = self._get_price(code, t.get("is_gold", False))
            if price <= 0:
                self.log(f"{name} 无价格数据")
                continue

            stop_loss = t.get("stop_loss")
            add_pos = t.get("add_position")

            # 止损位（首次跌破触发）
            if stop_loss and price < stop_loss:
                key = f"stop_{code}_{self.today}"
                if not self.state.has(key) or self.force:
                    alerts.append(f"🔻 {name} 跌破止损位: {price:.2f} < {stop_loss}")
                    teachings.append(price_alert_teaching(name, price, stop_loss, "down"))
                    self.state.set(key)

            # 加仓位（首次突破触发）
            if add_pos and price > add_pos:
                key = f"add_{code}_{self.today}"
                if not self.state.has(key) or self.force:
                    alerts.append(f"🔺 {name} 突破加仓位: {price:.2f} > {add_pos}")
                    teachings.append(price_alert_teaching(name, price, add_pos, "up"))
                    self.state.set(key)

            # 回到区间清 marker
            if stop_loss and price > stop_loss * 1.01:
                self.state.set(f"stop_{code}_{self.today}", False)
            if add_pos and price < add_pos * 0.99:
                self.state.set(f"add_{code}_{self.today}", False)

        if not alerts and not self.force:
            self.log(f"{self.now_str} 关键点位平稳")
            self.state.save()
            return True

        parts = [f"🎯 关键点位监控 ({self.now_str})"]
        parts.extend(alerts if alerts else ["✅ 所有点位正常"])
        if teachings:
            parts.append("")  # 空行分隔
            parts.append("\n\n".join(teachings))

        message = "\n".join(parts)
        if self.send(message):
            self.log(f"✅ 已发送 {self.now_str}")
            self.state.save()
            return True
        return False
