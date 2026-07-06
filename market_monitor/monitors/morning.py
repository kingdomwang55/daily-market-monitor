"""晨间市场报告(全球市场 + AI 分析)"""
from ..core.base import BaseMonitor
from ..core import data_source as ds
from ..core.ai import ai_chat
from ..core.data_source import _to_float
from ..core.teaching import get_daily_tip


class MorningMonitor(BaseMonitor):
    name = "morning"
    display_name = "晨间报告"

    #: 晨报标的
    A_INDICES = [
        ("sh000001", "上证指数"),
        ("sz399001", "深证成指"),
        ("sh000688", "科创50"),
        ("sz399006", "创业板指"),
    ]
    HK_INDICES = [
        ("hkHSI", "恒生指数"),
        ("hkHSTECH", "恒生科技"),
    ]
    US_INDICES = [
        ("gb_dji", "道琼斯"),
        ("gb_ixic", "纳斯达克"),
        ("gb_inx", "标普500"),
    ]
    # 额外补充：VIX / 美债10Y（Yahoo）
    YAHOO_EXTRAS = [
        ("^VIX", "VIX"),
        ("^TNX", "美债10Y"),
    ]
    COMMODITIES = [
        ("hf_CL", "WTI原油", "hf"),
        ("hf_SI", "COMEX白银", "hf"),
        ("nf_AU0", "沪金主力", "nf"),
        ("nf_AG0", "沪银主力", "nf"),
    ]
    DXY_CODE = "DINIW"

    def _fetch_all(self):
        """一次性拉所有数据"""
        all_codes = (
            [c for c, _ in self.A_INDICES]
            + [c for c, _ in self.HK_INDICES]
            + [c for c, _ in self.US_INDICES]
            + [c for c, _, _ in self.COMMODITIES]
            + [self.DXY_CODE]
        )
        mapping = ds.sina_map(all_codes)
        data = {}

        for code, name in self.A_INDICES:
            if code in mapping:
                info = ds.parse_a_index_full(mapping[code])
                if info:
                    data[name] = info

        for code, name in self.HK_INDICES:
            if code in mapping:
                info = ds.parse_hk_index_full(mapping[code])
                if info:
                    data[name] = info

        for code, name in self.US_INDICES:
            if code in mapping:
                info = ds.parse_us_v2(mapping[code])
                if info:
                    data[name] = info

        for code, name, kind in self.COMMODITIES:
            if code in mapping:
                if kind == "hf":
                    info = ds.parse_hf_commodity(mapping[code])
                else:
                    info = ds.parse_nf_futures(mapping[code])
                if info:
                    data[name] = info

        if self.DXY_CODE in mapping:
            info = ds.parse_dxy(mapping[self.DXY_CODE])
            if info:
                data["美元指数"] = info

        # Yahoo 拉 VIX / 美债10Y
        for symbol, name in self.YAHOO_EXTRAS:
            q = ds.yahoo_quote(symbol)
            if q:
                data[name] = q

        return data

    def _build_report(self, data):
        """生成文本快照"""
        now = self.now_str
        parts = [f"🌏 全球市场晨间简报", f"📅 {now}", ""]

        def _row(label, key, indent="  "):
            d = data.get(key)
            if not d:
                return f"{indent}{label:8s}: -"
            tag = ""
            stage = d.get("stage")
            if stage == "pre":
                tag = " [盘前]"
            elif stage == "closed":
                tag = " [-]"
            return f"{indent}{label:8s}: {d['price']:>10.2f} ({d['pct']:+.2f}%){tag}"

        parts.append("【隔夜美股】")
        parts.append(_row("道指", "道琼斯"))
        parts.append(_row("纳指", "纳斯达克"))
        parts.append(_row("标普500", "标普500"))

        parts.append("")
        parts.append("【港股】")
        parts.append(_row("恒指", "恒生指数"))
        parts.append(_row("恒科", "恒生科技"))

        parts.append("")
        parts.append("【A股(昨收)】")
        parts.append(_row("上证", "上证指数"))
        parts.append(_row("深成", "深证成指"))
        parts.append(_row("创业板", "创业板指"))
        parts.append(_row("科创50", "科创50"))

        parts.append("")
        parts.append("【大宗商品】")
        parts.append(_row("WTI原油", "WTI原油"))
        parts.append(_row("COMEX银", "COMEX白银"))
        parts.append(_row("沪金", "沪金主力"))
        parts.append(_row("沪银", "沪银主力"))

        parts.append("")
        parts.append("【风险指标】")
        parts.append(_row("VIX", "VIX"))
        # 美债10Y 单位是%
        us10y = data.get("美债10Y")
        if us10y:
            parts.append(f"  美债10Y  : {us10y['price']:>10.2f}% ({us10y['pct']:+.2f}%)")
        else:
            parts.append("  美债10Y  : -")

        parts.append("")
        parts.append("【汇市】")
        parts.append(_row("美元指数", "美元指数"))

        return "\n".join(parts)

    def _build_ai_prompt(self, data):
        """构造 AI 分析 prompt"""
        from datetime import datetime
        facts = []

        def _fact(label, key):
            d = data.get(key)
            if d:
                facts.append(f"{label}: {d['price']:.2f} ({d['pct']:+.2f}%)")

        facts.append("== 隔夜美股(前一交易日收盘)==")
        _fact("道琼斯", "道琼斯")
        _fact("纳斯达克", "纳斯达克")
        _fact("标普500", "标普500")

        facts.append("\n== 港股(前一日收盘)==")
        _fact("恒生指数", "恒生指数")
        _fact("恒生科技", "恒生科技")

        facts.append("\n== A 股(上一交易日收盘)==")
        _fact("上证指数", "上证指数")
        _fact("深证成指", "深证成指")
        _fact("科创50", "科创50")
        _fact("创业板指", "创业板指")

        facts.append("\n== 大宗商品 ==")
        _fact("WTI 原油", "WTI原油")
        _fact("COMEX 白银", "COMEX白银")
        _fact("沪金主力", "沪金主力")
        _fact("沪银主力", "沪银主力")

        facts.append("\n== 汇市 & 风险指标 ==")
        _fact("美元指数", "美元指数")
        _fact("VIX", "VIX")
        us10y = data.get("美债10Y")
        if us10y:
            facts.append(f"美债10Y收益率: {us10y['price']:.2f}% ({us10y['pct']:+.2f}%)")

        facts_text = "\n".join(facts)
        today = datetime.now().strftime("%Y-%m-%d %A")

        return f"""你是一位资深宏观策略师，正在为一位既懂交易又忙碌的中国投资者写晨间简报。请基于下方最新市场数据，生成一段简洁、专业、有观点的分析。

要求：
1. 分 4 段，依次为：
   【隔夜海外市场】、【A股/港股开盘预期与联动判断】、【大宗商品/汇率关注点】、【当日操作建议】
2. 【A股/港股开盘预期与联动判断】这一段重点：
   - 基于隔夜美股/DXY/VIX/美债10Y，预判今日A股开盘/行业方向
   - 提前标注哪些是“教科书式联动”（如 VIX急升 → A股高开低走），哪些可能出现“反直觉”（如 美股跌但 A 股可能拉拓，因为国内新政策等）
   - 晚上盘后报告会回验这些判断
3. 有明确观点（不要“可能/或许”堆砌），基于数据讲逻辑
4. 避免陈词滥调（“震荡整理”“谨慎观望”这类词请少用）
5. 中文，总字数控制在 380-480 字
6. 用【】标题分段，不要用 markdown 的 # 或 * 符号

市场数据：
{facts_text}

今天日期：{today}
"""

    def run(self) -> bool:
        # 防重发
        daily_key = f"morning_sent_{self.today}"
        if not self.force and self.state.has(daily_key):
            self.log(f"{self.now_str} 今天已发送过晨报")
            return True

        data = self._fetch_all()
        if not data:
            self.log("数据获取失败")
            return False

        report = self._build_report(data)

        # AI 分析
        prompt = self._build_ai_prompt(data)
        analysis = ai_chat(prompt, temperature=0.7, max_tokens=800)

        if analysis:
            report += f"\n\n━━━━━━━━━━━━━━━\n🤖 AI 市场解读\n\n{analysis}"
        else:
            report += "\n\n(AI 分析暂不可用)"

        # 每日教学锦囊(轮换)
        report += f"\n\n━━━━━━━━━━━━━━━\n{get_daily_tip()}"

        report += "\n\n(数据:新浪财经 · 分析:AI)"

        if self.send(report):
            self.state.set(daily_key)
            self.state.save()
            self.log(f"✅ 已发送 {self.now_str}")
            return True
        self.log("❌ 发送失败")
        return False
