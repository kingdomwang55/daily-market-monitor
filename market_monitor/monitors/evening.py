"""盘后市场报告（大盘+ETF+自选股+板块+异动榜+AI分析）"""
from ..core.base import BaseMonitor
from ..core import data_source as ds
from ..core.ai import ai_chat
from ..core.data_source import _to_float


class EveningMonitor(BaseMonitor):
    name = "evening"
    display_name = "盘后报告"

    INDICES = [
        ("sh000001", "上证指数"),
        ("sz399001", "深证成指"),
        ("sh000688", "科创50"),
        ("sz399006", "创业板指"),
    ]
    ETFS = [
        ("sh510300", "沪深300ETF"),
        ("sh510500", "中证500ETF"),
        ("sh512880", "证券ETF"),
    ]
    WATCHLIST = [
        ("sh600519", "贵州茅台"),
        ("sh600036", "招商银行"),
        ("sz000001", "平安银行"),
        ("sz002594", "比亚迪"),
        ("sz300750", "宁德时代"),
    ]

    def _gather_all(self):
        """收集所有数据"""
        result = {
            "indices": {},
            "etfs": {},
            "watchlist": {},
            "week_changes": {},
            "sectors_up": [],
            "sectors_down": [],
            "top_gainers": [],
            "top_losers": [],
        }

        # 指数
        for code, name in self.INDICES:
            q = ds.get_sina_quote(code)
            if q:
                result["indices"][name] = q

        # ETF
        for code, name in self.ETFS:
            q = ds.get_sina_quote(code)
            if q:
                result["etfs"][name] = q

        # 自选股
        for code, name in self.WATCHLIST:
            q = ds.get_sina_quote(code)
            if q:
                result["watchlist"][name] = q

        # 周对比
        for symbol, label in [("sh000001", "上证指数"), ("sz399006", "创业板指")]:
            wk = ds.calc_week_change(symbol)
            if wk is not None:
                result["week_changes"][label] = wk

        # 板块热度
        up, dn = ds.get_sector_hot(count=5)
        result["sectors_up"] = up
        result["sectors_down"] = dn

        # 异动榜
        gainers, losers = ds.get_top_movers(count=5)
        result["top_gainers"] = gainers
        result["top_losers"] = losers

        return result

    def _format_report(self, data):
        """生成文本报告"""
        lines = [f"📊 盘后市场深度报告", f"📅 {self.now_str}", ""]

        # 大盘
        lines.append("【大盘指数】")
        for name, q in data["indices"].items():
            wk = data["week_changes"].get(name)
            wk_str = f" | 周{wk:+.2f}%" if wk is not None else ""
            tag = " [盘前]" if q.get("stage") == "pre" else ""
            lines.append(f"  {name:8s}: {q['close']:>10.2f} ({q['pct']:+.2f}%){tag}{wk_str}")

        # ETF
        if data["etfs"]:
            lines.append("\n【ETF】")
            for name, q in data["etfs"].items():
                lines.append(f"  {name:10s}: {q['close']:>8.3f} ({q['pct']:+.2f}%)")

        # 自选股
        if data["watchlist"]:
            lines.append("\n【自选股】")
            for name, q in data["watchlist"].items():
                lines.append(f"  {name:8s}: {q['close']:>10.2f} ({q['pct']:+.2f}%)")

        # 板块涨
        if data["sectors_up"]:
            lines.append("\n【板块 · 涨幅 TOP5】")
            for s in data["sectors_up"]:
                pct = s.get("f3", 0)
                name = s.get("f14", "?")
                lines.append(f"  {name}: {pct:+.2f}%")

        # 板块跌
        if data["sectors_down"]:
            lines.append("\n【板块 · 跌幅 TOP5】")
            for s in data["sectors_down"]:
                pct = s.get("f3", 0)
                name = s.get("f14", "?")
                lines.append(f"  {name}: {pct:+.2f}%")

        # 涨幅榜
        if data["top_gainers"]:
            lines.append("\n【个股异动 · 涨幅榜】")
            for x in data["top_gainers"]:
                code = x.get("symbol", "")
                name = x.get("name", "")
                pct = _to_float(x.get("changepercent", 0))
                price = _to_float(x.get("trade", 0))
                lines.append(f"  {name}({code}): {price:.2f} ({pct:+.2f}%)")

        # 跌幅榜
        if data["top_losers"]:
            lines.append("\n【个股异动 · 跌幅榜】")
            for x in data["top_losers"]:
                code = x.get("symbol", "")
                name = x.get("name", "")
                pct = _to_float(x.get("changepercent", 0))
                price = _to_float(x.get("trade", 0))
                lines.append(f"  {name}({code}): {price:.2f} ({pct:+.2f}%)")

        return "\n".join(lines)

    def _build_ai_prompt(self, data):
        """构造 AI 分析 prompt"""
        from datetime import datetime
        facts = []

        facts.append("== 大盘 ==")
        for name, q in data["indices"].items():
            wk = data["week_changes"].get(name)
            wk_str = f"（周累计{wk:+.2f}%）" if wk is not None else ""
            facts.append(f"{name}: 收{q['close']:.2f}, 涨跌{q['pct']:+.2f}%{wk_str}")

        if data["etfs"]:
            facts.append("\n== ETF ==")
            for name, q in data["etfs"].items():
                facts.append(f"{name}: {q['close']:.3f} ({q['pct']:+.2f}%)")

        if data["watchlist"]:
            facts.append("\n== 自选股 ==")
            for name, q in data["watchlist"].items():
                facts.append(f"{name}: {q['close']:.2f} ({q['pct']:+.2f}%)")

        if data["sectors_up"]:
            facts.append("\n== 板块涨幅榜 ==")
            for s in data["sectors_up"]:
                facts.append(f"{s.get('f14')}: {s.get('f3', 0):+.2f}%")

        if data["sectors_down"]:
            facts.append("\n== 板块跌幅榜 ==")
            for s in data["sectors_down"]:
                facts.append(f"{s.get('f14')}: {s.get('f3', 0):+.2f}%")

        if data["top_gainers"]:
            facts.append("\n== 涨幅榜 TOP5（个股）==")
            for x in data["top_gainers"]:
                facts.append(f"{x.get('name')}: {_to_float(x.get('changepercent', 0)):+.2f}%")

        if data["top_losers"]:
            facts.append("\n== 跌幅榜 TOP5（个股）==")
            for x in data["top_losers"]:
                facts.append(f"{x.get('name')}: {_to_float(x.get('changepercent', 0)):+.2f}%")

        facts_text = "\n".join(facts)
        today = datetime.now().strftime("%Y-%m-%d %A")

        # 盘前防呆
        all_zero = all(
            q.get("pct", 0) == 0 and q.get("stage") != "live"
            for q in data["indices"].values()
        ) if data["indices"] else False
        stage_hint = ""
        if all_zero:
            stage_hint = (
                '\n【重要提示】当前所有指数涨跌均为 0，'
                '说明未开盘或数据接口异常，请直接回复：'
                '"❗ 当前未开盘或行情数据未更新，无盘后内容可分析。"'
                '不要臆测任何结论。\n'
            )

        return f"""你是一位资深A股策略师，正在为一位既懂交易又忙碌的中国投资者写盘后深度报告。基于下方今日收盘数据，输出简洁、专业、有观点的分析。
{stage_hint}
要求：
1. 4-5 段短评，覆盖：今日大盘特征、板块轮动逻辑、异动信号、自选股解读、明日操作建议
2. 有明确观点（不要"可能/或许"堆砌），基于数据讲逻辑
3. 避免陈词滥调（"震荡整理""谨慎观望"少用）
4. 中文，总字数控制在 350-500 字
5. 用【】标题分段，不要用 markdown 的 # 或 * 符号
6. 若板块数据全为 0（说明未开盘），只做已有数据的分析，不要臆测

今日日期：{today}

市场数据：
{facts_text}
"""

    def run(self) -> bool:
        # 防重发
        daily_key = f"evening_sent_{self.today}"
        if not self.force and self.state.has(daily_key):
            self.log(f"{self.now_str} 今天已发送过盘后报告")
            return True

        data = self._gather_all()
        report = self._format_report(data)

        # AI 分析
        prompt = self._build_ai_prompt(data)
        analysis = ai_chat(prompt, temperature=0.7, max_tokens=1000)

        if analysis:
            report += f"\n\n━━━━━━━━━━━━━━━\n🤖 AI 市场解读\n\n{analysis}"
        else:
            report += "\n\n（AI 分析暂不可用）"

        report += "\n\n（数据：新浪财经/东财 · 分析：AI）"

        if self.send(report):
            self.state.set(daily_key)
            self.state.save()
            self.log(f"✅ 已发送 {self.now_str}")
            return True
        self.log("❌ 发送失败")
        return False
