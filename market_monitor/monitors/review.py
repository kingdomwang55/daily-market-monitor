"""周报复盘 Monitor（每周日晚自动运行）

流程：
1. 自动 extract + verify 本周所有工作日的决策
2. 生成周报复盘报告
3. 推送到飞书
"""
from ..core.base import BaseMonitor
from ..core import decision_tracker as dt
from ..core import push_logger
from datetime import datetime, timedelta


class ReviewMonitor(BaseMonitor):
    name = "review"
    display_name = "周报复盘"

    def run(self) -> bool:
        today = self.now.date()
        # 只在周日运行（除非 --force）
        if today.weekday() != 6 and not self.force:
            self.log(f"今天不是周日（{today}），跳过（--force 可强制）")
            return True

        # 防重发：本周日已经推过？
        week_key = f"review_{today.strftime('%Y-W%W')}"
        if self.state.has(week_key) and not self.force:
            self.log(f"本周周报已推送（{week_key}），跳过")
            return True

        # 本周一 → 周日
        monday = today - timedelta(days=today.weekday())
        start = monday.strftime("%Y-%m-%d")
        end = today.strftime("%Y-%m-%d")

        # 1. 对本周末校验的日进行 extract + verify
        cursor = monday
        while cursor <= today:
            ds_str = cursor.strftime("%Y-%m-%d")
            decisions = dt.list_decisions(ds_str)

            # 如果有推送日志但还没提取 → 自动提取
            if not decisions:
                records = push_logger.read_day(ds_str)
                if records:
                    self.log(f"{ds_str} 有推送记录，自动提取…")
                    decisions = dt.extract_decisions(ds_str)

            # 校验（跳过已校验的）
            need_verify = [d for d in decisions if not d.get("verdict")]
            if need_verify:
                self.log(f"{ds_str} 有 {len(need_verify)} 条待校验")
                dt.verify_decisions(ds_str)

            cursor += timedelta(days=1)

        # 2. 生成周报
        report = dt.format_weekly_review(start, end)

        # 3. 推送
        if self.send(report, meta={"start": start, "end": end}):
            self.state.set(week_key)
            self.state.save()
            self.log(f"✅ 周报已推送: {start} → {end}")
            return True

        self.log("❌ 周报推送失败")
        return False
