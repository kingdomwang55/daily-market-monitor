"""月报复盘 Monitor（每月 1 号 09:00 自动运行）

流程：
1. 生成上月胜率报告（decision_tracker.format_monthly_review）
2. 拼接本月宏观日历（calendar_events.in_month）
3. 推送到飞书
"""
from ..core.base import BaseMonitor
from ..core import decision_tracker as dt
from ..core import calendar_events as cal
from datetime import datetime, timedelta


class MonthlyMonitor(BaseMonitor):
    name = "monthly"
    display_name = "月报复盘"

    def run(self) -> bool:
        today = self.now.date()

        # 只在每月 1 号运行（除非 --force）
        if today.day != 1 and not self.force:
            self.log(f"今天不是月初（{today}），跳过（--force 可强制）")
            return True

        # 防重发：本月已推？
        month_key = f"monthly_{today.strftime('%Y-%m')}"
        if self.state.has(month_key) and not self.force:
            self.log(f"本月月报已推送（{month_key}），跳过")
            return True

        # 上个月
        if today.month == 1:
            last_year, last_month = today.year - 1, 12
        else:
            last_year, last_month = today.year, today.month - 1

        # 本月
        this_year, this_month = today.year, today.month

        # 1. 生成上月复盘
        review_report = dt.format_monthly_review(last_year, last_month)

        # 2. 拼接本月宏观日历
        events = cal.in_month(this_year, this_month)

        calendar_section = (
            f"\n---\n\n"
            f"## 🗓️ 本月宏观日历（{this_year}-{this_month:02d}）\n\n"
        )
        if events:
            # 只显示影响力 ≥ 4 的（重要事件）
            important = [e for e in events if e["impact"] >= 4]
            if important:
                calendar_section += cal.format_events(important, show_days_from_now=False)
            else:
                calendar_section += "（本月无重大宏观事件）"
        else:
            calendar_section += "（本月暂无录入的宏观事件）"

        # 3. 主题建议
        theme_section = (
            f"\n\n---\n\n"
            f"## 🎯 本月主题建议\n\n"
            f"> 结合上月表现 + 本月日历，为自己定 1-2 个操作原则：\n\n"
            f"- **本月重点关注**：\n"
            f"- **风险规避事项**：\n"
            f"- **实验/学习计划**：\n"
        )

        report = review_report + calendar_section + theme_section

        # 4. 推送
        if self.send(report, meta={
            "review_month": f"{last_year}-{last_month:02d}",
            "calendar_month": f"{this_year}-{this_month:02d}",
        }):
            self.state.set(month_key)
            self.state.save()
            self.log(f"✅ 月报已推送: {last_year}-{last_month:02d}")
            return True

        self.log("❌ 月报推送失败")
        return False
