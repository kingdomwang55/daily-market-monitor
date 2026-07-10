"""晨间市场报告(全球市场 + AI 分析)"""
from ..core.base import BaseMonitor
from ..core import data_source as ds
from ..core.ai import ai_chat
from ..core.data_source import _to_float
from ..core.teaching import get_daily_tip
from ..core import cross_asset
from ..core import lookahead
from ..core import forex as fx
from ..core import bonds as bd
from ..core import sentiment as st
from ..core import geopolitics as geo
from ..core import scenario as sc


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
        ("hf_GC", "COMEX金", "hf"),
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

        # P1: 外汇扩展
        try:
            data["_forex"] = fx.fetch_forex()
        except Exception as e:
            print(f"[morning] 外汇数据获取失败: {e}")

        # P1: 债券曲线
        try:
            data["_bonds"] = bd.fetch_bonds()
            data["_spreads"] = bd.calc_spreads(data["_bonds"])
        except Exception as e:
            print(f"[morning] 债券数据获取失败: {e}")

        # P1: 情绪指标
        try:
            data["_sentiment"] = st.fetch_sentiment()
        except Exception as e:
            print(f"[morning] 情绪数据获取失败: {e}")

        # P2-2: 地缘事件
        try:
            data["_geo_events"] = geo.fetch_geo_events(hours=24)
        except Exception as e:
            print(f"[morning] 地缘事件获取失败: {e}")

        # 泪深港通资金流（昨日收盘确定值 + 近5日趋势）
        try:
            data["_south_latest"] = ds.fetch_south_flow_latest()
            data["_south_trend"] = ds.fetch_south_flow_trend(days=5)
            data["_north_deal"] = ds.fetch_north_deal_latest()
        except Exception as e:
            print(f"[morning] 资金流获取失败: {e}")

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
        # 黄金统一用美元/盎司为主，括号备注人民币/克（Steven 偏好）
        from ..core.gold_price import format_gold
        comex_g = data.get("COMEX金")
        shg = data.get("沪金主力")
        if comex_g or shg:
            parts.append(
                "  黄金    : "
                + format_gold(
                    usd_per_oz=comex_g["price"] if comex_g else None,
                    cny_per_gram=shg["price"] if shg else None,
                    pct=comex_g["pct"] if comex_g else (shg["pct"] if shg else None),
                    label="",
                ).strip()
            )
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

        # 外汇扩展（P1-1）
        forex_data = data.get("_forex") or {}
        if forex_data:
            parts.append("")
            parts.append(fx.format_forex(forex_data))

        # 债券曲线（P1-2）
        bonds_data = data.get("_bonds") or {}
        spreads = data.get("_spreads") or {}
        if bonds_data:
            parts.append("")
            parts.append(bd.format_bonds(bonds_data, spreads))

        # 情绪指标（P1-3）
        sentiment_data = data.get("_sentiment") or {}
        if sentiment_data:
            parts.append("")
            parts.append(st.format_sentiment(sentiment_data))

        # P2-2: 地缘事件
        geo_events = data.get("_geo_events") or []
        if geo_events:
            parts.append("")
            parts.append(geo.format_geo_brief(geo_events, top=6))

        # 泪深港通资金流
        south = data.get("_south_latest") or {}
        north = data.get("_north_deal") or {}
        south_net = south.get("net") if south else None
        if south_net is not None or north:
            parts.append("")
            parts.append("【泪深港通资金（昨日收盘）】")
            if south_net is not None:
                arrow = "🟢" if south_net >= 0 else "🔴"
                parts.append(f"  南下资金  : {south_net:+.2f} 亿 {arrow}")
            north_deal = north.get("deal") if north else None
            if north_deal is not None:
                parts.append(f"  北向成交  : {north_deal:.0f} 亿")
            trend = data.get("_south_trend") or []
            trend_nets = [t.get("net") for t in trend if t.get("net") is not None]
            if trend_nets:
                total = sum(trend_nets)
                pos = sum(1 for n in trend_nets if n > 0)
                neg = len(trend_nets) - pos
                parts.append(
                    f"  近{len(trend_nets)}日累计: {total:+.2f} 亿 ({pos}入/{neg}出)"
                )

        return "\n".join(parts)

    def _build_ai_prompt(self, data, signals=None):
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
        # 黄金：美元/盎司为主，人民币/克备注
        from ..core.gold_price import format_gold
        comex_g = data.get("COMEX金")
        shg = data.get("沪金主力")
        if comex_g or shg:
            facts.append(
                "黄金: "
                + format_gold(
                    usd_per_oz=comex_g["price"] if comex_g else None,
                    cny_per_gram=shg["price"] if shg else None,
                    pct=comex_g["pct"] if comex_g else (shg["pct"] if shg else None),
                    label="",
                ).strip()
            )
        _fact("沪银主力", "沪银主力")

        facts.append("\n== 汇市 & 风险指标 ==")
        _fact("美元指数", "美元指数")
        _fact("VIX", "VIX")
        us10y = data.get("美债10Y")
        if us10y:
            facts.append(f"美债10Y收益率: {us10y['price']:.2f}% ({us10y['pct']:+.2f}%)")

        # 泪深港通资金流（昨日收盘值 + 近5日趋势）
        south = data.get("_south_latest") or {}
        north = data.get("_north_deal") or {}
        south_net = south.get("net") if south else None
        if south_net is not None or north:
            facts.append("\n== 泪深港通资金流（昨日收盘）==")
            if south_net is not None:
                direction = "流入" if south_net >= 0 else "流出"
                facts.append(f"南下资金: 净{direction} {south_net:+.2f} 亿（{south.get('date','')}）")
            north_deal = north.get("deal") if north else None
            if north_deal is not None:
                facts.append(f"北向成交额: {north_deal:.0f} 亿（净买入厣交所已停公布，仅成交额）")
            trend = data.get("_south_trend") or []
            trend_nets = [t.get("net") for t in trend if t.get("net") is not None]
            if trend_nets and len(trend_nets) >= 3:
                total = sum(trend_nets)
                pos = sum(1 for n in trend_nets if n > 0)
                neg = len(trend_nets) - pos
                facts.append(f"南下近{len(trend_nets)}日累计: {total:+.2f} 亿 ({pos} 日净流入 / {neg} 日净流出)")

        facts_text = "\n".join(facts)
        today = datetime.now().strftime("%Y-%m-%d %A")

        # 跨资产传导信号（规则引擎输出）
        signals_text = cross_asset.signals_summary_for_ai(signals or [])
        # 财经日历（今日 + 未来3天）
        cal_text = lookahead.build_morning_calendar_brief() or "财经日历：本周无高影响事件"

        # P1: 外汇/债券/情绪 紧凑版
        forex_text = fx.forex_summary_for_ai(data.get("_forex") or {})
        bonds_text = bd.bonds_summary_for_ai(data.get("_bonds") or {}, data.get("_spreads") or {})
        sentiment_text = st.sentiment_summary_for_ai(data.get("_sentiment") or {})

        # P2-2: 地缘事件
        geo_events = data.get("_geo_events") or []
        geo_text = geo.geo_summary_for_ai(geo_events, top=6)

        # P2-3: 情景推演（从日历中匹配高影响事件）
        import importlib.util  # noqa: F811
        spec = importlib.util.find_spec("market_monitor.core.econ_calendar")
        if spec:
            from market_monitor.core.econ_calendar import today_events, upcoming
            cal_events = today_events() + upcoming(3)
            high_impact_evs = [e for e in cal_events if e.get("impact_score", 0) >= 4]
            scenario_text = sc.format_scenarios_for_calendar(high_impact_evs)
        else:
            scenario_text = ""

        return f"""你是一位资深宏观策略师，正在为一位既懂交易又忙碌的中国投资者写晨间简报。请基于下方最新市场数据，生成一段简洁、专业、有观点的分析。

要求：
1. 分 5 段，依次为：
   【隔夜海外市场】、【跨资产传导叙事】、【A股/港股开盘预期与联动判断】、【今日关注（日历）】、【当日操作建议】
2. 【跨资产传导叙事】只能使用下方“规则引擎”检测到的信号，把它们串成一段因果叙事，不要就单一数据孤立解读；若无信号则写“今日未触发显著传导链，属于细碎行情”
3. 【A股/港股开盘预期与联动判断】这一段重点：
   - 基于隔夜美股/DXY/VIX/美债10Y，预判今日A股开盘/行业方向
   - 提前标注哪些是“教科书式联动”（如 VIX急升 → A股高开低走），哪些可能出现“反直觉”（如 美股跌但 A 股可能拉拓，因为国内新政策等）
   - 晚上盘后报告会回验这些判断
   - 如数据中有泪深港通资金流，必须把昨日南下资金方向 + 近5日累计纳入港股开盘预判：
     • 南下流入 = 内资看多港股，高股息/科技龙头可能旹盘受益
     • 南下流出 = 内资撤退，港股短期承压，也会拖累 A 股同板块
4. 【今日关注（日历）】把下方财经日历信息自然融入：重点说明影响时间点 + 预期值 vs 前值 + 若超预期可能的传导链
5. 有明确观点（不要“可能/或许”堆砌），基于数据讲逻辑
6. 避免陈词滥调（“震荡整理”“谨慎观望”这类词请少用）
7. 中文，总字数控制在 500-650 字
8. 用【】标题分段，不要用 markdown 的 # 或 * 符号

市场数据：
{facts_text}

{forex_text}

{bonds_text}

{sentiment_text}

{geo_text}

{signals_text}

{cal_text}

{scenario_text}

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

        # 跨资产联动分析
        signals = cross_asset.analyze(data)
        if signals:
            report += f"\n\n━━━━━━━━━━━━━━━\n🔗 跨资产传导信号\n\n{cross_asset.format_signals(signals)}"

        # P1: 外汇异动信号
        forex_data = data.get("_forex") or {}
        fx_signals = fx.analyze_forex_signals(forex_data)
        if fx_signals:
            fx_lines = ["\n━━━━━━━━━━━━━━━\n💱 外汇异动信号\n"]
            for s in fx_signals:
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s["severity"], "•")
                fx_lines.append(f"{icon} 【{s['name']}】 {s['narrative']}")
            report += "\n".join(fx_lines)

        # P1: 债券曲线信号
        bonds_data = data.get("_bonds") or {}
        spreads = data.get("_spreads") or {}
        bond_signals = bd.analyze_yield_curve(bonds_data, spreads)
        if bond_signals:
            bd_lines = ["\n━━━━━━━━━━━━━━━\n📈 债券曲线信号\n"]
            for s in bond_signals:
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s["severity"], "•")
                bd_lines.append(f"{icon} 【{s['name']}】\n  {s['narrative']}")
            report += "\n".join(bd_lines)

        # P1: 情绪极端信号
        sentiment_data = data.get("_sentiment") or {}
        sent_signals = st.analyze_sentiment_signals(sentiment_data)
        if sent_signals:
            sent_lines = ["\n━━━━━━━━━━━━━━━\n🧠 情绪极端信号\n"]
            for s in sent_signals:
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s["severity"], "•")
                sent_lines.append(f"{icon} 【{s['name']}】\n  {s['narrative']}")
            report += "\n".join(sent_lines)

        # 财经日历
        cal_brief = lookahead.build_morning_calendar_brief()
        if cal_brief:
            report += f"\n\n{cal_brief}"

        # AI 分析
        prompt = self._build_ai_prompt(data, signals)
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
