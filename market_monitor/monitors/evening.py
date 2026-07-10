"""盘后市场报告(大盘+ETF+自选股+板块+异动榜+AI分析)"""
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
from ..core import sector_flow as sf
from ..core import geopolitics as geo
from ..core import scenario as sc
from ..core import position_tracker as pos_trk
from ..core import ah_premium as ah
from ..core import etf_premium as etf
from ..core import index_valuation as iv


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

    # 国际市场(前一交易日收盘/最新)
    OVERSEAS_SINA = [
        ("gb_dji", "道琼斯", "us"),
        ("gb_ixic", "纳斯达克", "us"),
        ("gb_inx", "标普500", "us"),
        ("hf_CL", "WTI原油", "hf"),
        ("hf_GC", "COMEX金", "hf"),
        ("hf_SI", "COMEX白银", "hf"),
        ("nf_AU0", "沪金主力", "nf"),
        ("DINIW", "美元指数", "dxy"),
    ]
    OVERSEAS_YAHOO = [
        ("^VIX", "VIX"),
        ("^TNX", "美债10Y"),  # CBOE 10Y 国债收益率指数,直接就是百分比数值,如 4.485 = 4.485%
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
            "overseas": {},
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

        # 国际市场(新浪 + Yahoo)
        sina_codes = [c for c, _, _ in self.OVERSEAS_SINA]
        mapping = ds.sina_map(sina_codes)
        for code, name, kind in self.OVERSEAS_SINA:
            if code not in mapping:
                continue
            line = mapping[code]
            info = None
            if kind == "us":
                info = ds.parse_us_v2(line)
            elif kind == "hf":
                info = ds.parse_hf_commodity(line)
            elif kind == "nf":
                info = ds.parse_nf_futures(line)
            elif kind == "dxy":
                info = ds.parse_dxy(line)
            if info:
                result["overseas"][name] = info

        for symbol, name in self.OVERSEAS_YAHOO:
            q = ds.yahoo_quote(symbol)
            if q:
                result["overseas"][name] = q

        # 泪深港通资金流（当日收盘值）
        try:
            result["south_latest"] = ds.fetch_south_flow_latest()
            result["south_trend"] = ds.fetch_south_flow_trend(days=5)
            result["north_deal"] = ds.fetch_north_deal_latest()
        except Exception as e:
            print(f"[evening] 资金流获取失败: {e}")
            result["south_latest"] = None
            result["south_trend"] = []
            result["north_deal"] = None

        # P1: 外汇/债券/情绪
        try:
            result["forex"] = fx.fetch_forex()
        except Exception as e:
            print(f"[evening] 外汇数据获取失败: {e}")
            result["forex"] = {}
        try:
            result["bonds"] = bd.fetch_bonds()
            result["spreads"] = bd.calc_spreads(result["bonds"])
        except Exception as e:
            print(f"[evening] 债券数据获取失败: {e}")
            result["bonds"] = {}
            result["spreads"] = {}
        try:
            result["sentiment"] = st.fetch_sentiment()
        except Exception as e:
            print(f"[evening] 情绪数据获取失败: {e}")
            result["sentiment"] = {}

        # P2-1: 板块资金流
        try:
            result["sector_flow"] = sf.fetch_sector_flow(kind="industry", top_n=50)
        except Exception as e:
            print(f"[evening] 板块资金流获取失败: {e}")
            result["sector_flow"] = []

        # P2-2: 地缘事件
        try:
            result["geo_events"] = geo.fetch_geo_events(hours=24)
        except Exception as e:
            print(f"[evening] 地缘事件获取失败: {e}")
            result["geo_events"] = []

        # P3-1: 仓位健康度
        try:
            pos_data = pos_trk.load_positions()
            if pos_data.get("positions"):
                pos_prices = pos_trk.fetch_current_prices(pos_data)
                # 对于没有 symbol 的持仓，用 entry_price 兜底
                for p in pos_data["positions"]:
                    if p["id"] not in pos_prices:
                        pos_prices[p["id"]] = float(p.get("entry_price", 0))
                result["position_health"] = pos_trk.calc_position_health(pos_data, pos_prices)
            else:
                result["position_health"] = None
        except Exception as e:
            print(f"[evening] 仓位健康度获取失败: {e}")
            result["position_health"] = None

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

        # 国际市场(前一交易日)
        if data.get("overseas"):
            lines.append("\n【前一交易日 · 国际市场】")
            # 黄金统一展示（美元/盎司 + 人民币/克）——Steven 偏好
            comex_g = data["overseas"].pop("COMEX金", None)
            shg = data["overseas"].pop("沪金主力", None)
            for name, q in data["overseas"].items():
                price = q.get("price", q.get("close", 0))
                pct = q.get("pct", 0)
                unit = "%" if name == "美债10Y" else ""
                lines.append(f"  {name:8s}: {price:>10.2f}{unit} ({pct:+.2f}%)")
            if comex_g or shg:
                from ..core.gold_price import format_gold
                gold_line = format_gold(
                    usd_per_oz=comex_g["price"] if comex_g else None,
                    cny_per_gram=shg["price"] if shg else None,
                    pct=comex_g["pct"] if comex_g else (shg["pct"] if shg else None),
                    label="",
                ).strip()
                lines.append(f"  黄金    : {gold_line}")
            # 把取出的金价还回字典（供后续 AI/交叉信号使用）
            if comex_g:
                data["overseas"]["COMEX金"] = comex_g
            if shg:
                data["overseas"]["沪金主力"] = shg

        # 泪深港通资金流
        south = data.get("south_latest") or {}
        north = data.get("north_deal") or {}
        south_net = south.get("net") if south else None
        if south_net is not None or north:
            lines.append("\n【泪深港通资金流】")
            if south_net is not None:
                arrow = "🟢" if south_net >= 0 else "🔴"
                lines.append(f"  南下资金  : {south_net:+.2f} 亿 {arrow}（{south.get('date','')}）")
            north_deal = north.get("deal") if north else None
            if north_deal is not None:
                lines.append(f"  北向成交  : {north_deal:.0f} 亿")
            trend = data.get("south_trend") or []
            trend_nets = [t.get("net") for t in trend if t.get("net") is not None]
            if trend_nets:
                total = sum(trend_nets)
                pos = sum(1 for n in trend_nets if n > 0)
                neg = len(trend_nets) - pos
                lines.append(
                    f"  近{len(trend_nets)}日累计: {total:+.2f} 亿 ({pos}入/{neg}出)"
                )

        # P1: 外汇/债券/情绪
        forex_data = data.get("forex") or {}
        if forex_data:
            lines.append("\n" + fx.format_forex(forex_data))

        bonds_data = data.get("bonds") or {}
        spreads = data.get("spreads") or {}
        if bonds_data:
            lines.append("\n" + bd.format_bonds(bonds_data, spreads))

        sentiment_data = data.get("sentiment") or {}
        if sentiment_data:
            lines.append("\n" + st.format_sentiment(sentiment_data))

        # P2-1: 板块资金流
        sector_items = data.get("sector_flow") or []
        if sector_items:
            lines.append("\n" + sf.format_sector_flow(sector_items, top=5))

        # P2-2: 地缘事件
        geo_events = data.get("geo_events") or []
        if geo_events:
            lines.append("\n" + geo.format_geo_brief(geo_events, top=8))

        return "\n".join(lines)

    def _build_ai_prompt(self, data, signals=None):
        """构造 AI 分析 prompt"""
        from datetime import datetime
        facts = []

        facts.append("== 大盘 ==")
        for name, q in data["indices"].items():
            wk = data["week_changes"].get(name)
            wk_str = f"(周累计{wk:+.2f}%)" if wk is not None else ""
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
            facts.append("\n== 涨幅榜 TOP5(个股)==")
            for x in data["top_gainers"]:
                facts.append(f"{x.get('name')}: {_to_float(x.get('changepercent', 0)):+.2f}%")

        if data["top_losers"]:
            facts.append("\n== 跌幅榜 TOP5（个股）==")
            for x in data["top_losers"]:
                facts.append(f"{x.get('name')}: {_to_float(x.get('changepercent', 0)):+.2f}%")

        if data.get("overseas"):
            facts.append("\n== 国际市场（前一交易日收盘）==")
            for name, q in data["overseas"].items():
                price = q.get("price", q.get("close", 0))
                pct = q.get("pct", 0)
                unit = "%" if name == "美债10Y" else ""
                facts.append(f"{name}: {price:.2f}{unit} ({pct:+.2f}%)")

        # 泪深港通资金流（收盘确定值）
        south = data.get("south_latest") or {}
        north = data.get("north_deal") or {}
        south_net = south.get("net") if south else None
        if south_net is not None or north:
            facts.append("\n== 泪深港通资金流 ==")
            if south_net is not None:
                direction = "流入" if south_net >= 0 else "流出"
                facts.append(f"南下资金: 净{direction} {south_net:+.2f} 亿（{south.get('date','')}）")
            north_deal = north.get("deal") if north else None
            if north_deal is not None:
                facts.append(f"北向成交额: {north_deal:.0f} 亿（注：净买入厣交所已停公布）")
            trend = data.get("south_trend") or []
            trend_nets = [t.get("net") for t in trend if t.get("net") is not None]
            if trend_nets and len(trend_nets) >= 3:
                total = sum(trend_nets)
                pos = sum(1 for n in trend_nets if n > 0)
                neg = len(trend_nets) - pos
                facts.append(f"南下近{len(trend_nets)}日累计: {total:+.2f} 亿 ({pos}日净流入 / {neg}日净流出)")

        facts_text = "\n".join(facts)
        today = datetime.now().strftime("%Y-%m-%d %A")

        # 跨资产传导信号（规则引擎输出，给 AI 当作国际市场联动分析的输入）
        signals_text = cross_asset.signals_summary_for_ai(signals or [])

        # P1: 外汇/债券/情绪
        p1_forex = fx.forex_summary_for_ai(data.get("forex") or {})
        p1_bonds = bd.bonds_summary_for_ai(data.get("bonds") or {}, data.get("spreads") or {})
        p1_sentiment = st.sentiment_summary_for_ai(data.get("sentiment") or {})

        # P2-1: 板块资金流
        sector_items = data.get("sector_flow") or []
        p2_sector = sf.sector_flow_summary_for_ai(sector_items, top=8)
        sector_signals = sf.analyze_sector_rotation(sector_items)
        p2_sector_signals = sf.sector_signals_summary_for_ai(sector_signals)

        # P2-2: 地缘事件
        geo_events = data.get("geo_events") or []
        p2_geo = geo.geo_summary_for_ai(geo_events, top=8)

        # P2-3: 情景推演（从日历中匹配高影响事件）
        import importlib.util
        spec = importlib.util.find_spec("market_monitor.core.econ_calendar")
        if spec:
            from market_monitor.core.econ_calendar import today_events, upcoming
            cal_events = today_events() + upcoming(3)
            high_impact_evs = [e for e in cal_events if e.get("impact_score", 0) >= 4]
            p2_scenario = sc.format_scenarios_for_calendar(high_impact_evs)
        else:
            p2_scenario = ""

        # P3-1: 仓位健康度摘要
        health = data.get("position_health")
        p3_position = pos_trk.signals_summary_for_ai(health) if health else ""

        # 盘前防呆
        all_zero = all(
            q.get("pct", 0) == 0 and q.get("stage") != "live"
            for q in data["indices"].values()
        ) if data["indices"] else False
        stage_hint = ""
        if all_zero:
            stage_hint = (
                '\n【重要提示】当前所有指数涨跌均为 0,'
                '说明未开盘或数据接口异常,请直接回复:'
                '"❗ 当前未开盘或行情数据未更新,无盘后内容可分析。"'
                '不要臆测任何结论。\n'
            )

        return f"""你是一位资深A股策略师，正在为一位既懂交易又忙碌的中国投资者写盘后深度报告。基于下方今日收盘数据，输出简洁、专业、有观点的分析。
{stage_hint}
要求：
1. 分 5 段，依次为：
   【今日大盘特征】、【板块轮动逻辑】、【国际市场联动分析】、【异动/自选股解读】、【明日操作建议】
2. 【国际市场联动分析】这一段非常关键，要求：
   - 把前一交易日的国际市场（美股/大宗/DXY/VIX/美债10Y）与今日A股、行业板块、汇率表现逐条对映
   - 分两类列出：
     ✅ 正常联动：“→” 符号描述叠动关系（如：隔夜VIX回落10% → A股风险股大液）
     ⚠️ 反直觉信号：列举“本应xxx 但实际xxx”的背离，并让你给出 1 句背后可能的逻辑（而不是“不确定”）
   - 至少 3 条正常 + 1-2 条反直觉（确实没反直觉信号才可写“今日无明显背离”）
3. 有明确观点（不要“可能/或许”堆砌），基于数据讲逻辑
4. 避免陈词滥调（“震荡整理”“谨慎观望”少用）
5. 中文，总字数 500-650 字
6. 用【】标题分段，不要用 markdown 的 # 或 * 符号
7. 若板块数据全为 0（未开盘），只做已有数据的分析，不要臆测

今日日期：{today}

市场数据：
{facts_text}

{p1_forex}

{p1_bonds}

{p1_sentiment}

{p2_sector}

{p2_sector_signals}

{p2_geo}

{p2_scenario}

{p3_position}

{signals_text}
"""

    def run(self) -> bool:
        # 防重发
        daily_key = f"evening_sent_{self.today}"
        if not self.force and self.state.has(daily_key):
            self.log(f"{self.now_str} 今天已发送过盘后报告")
            return True

        data = self._gather_all()
        report = self._format_report(data)

        # 跨资产传导信号（基于国际市场数据）
        overseas_for_ca = dict(data.get("overseas") or {})
        # 把南下资金也接进去（以 _south_latest 为 key，匹配 cross_asset 的约定）
        if data.get("south_latest"):
            overseas_for_ca["_south_latest"] = data["south_latest"]
        signals = cross_asset.analyze(overseas_for_ca)
        if signals:
            report += f"\n\n━━━━━━━━━━━━━━━\n🔗 跨资产传导信号\n\n{cross_asset.format_signals(signals)}"

        # P1: 外汇/债券/情绪 信号
        forex_data = data.get("forex") or {}
        fx_signals = fx.analyze_forex_signals(forex_data)
        if fx_signals:
            fx_lines = ["\n━━━━━━━━━━━━━━━\n💱 外汇异动信号\n"]
            for s in fx_signals:
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s["severity"], "•")
                fx_lines.append(f"{icon} 【{s['name']}】 {s['narrative']}")
            report += "\n".join(fx_lines)

        bonds_data = data.get("bonds") or {}
        spreads = data.get("spreads") or {}
        bond_signals = bd.analyze_yield_curve(bonds_data, spreads)
        if bond_signals:
            bd_lines = ["\n━━━━━━━━━━━━━━━\n📈 债券曲线信号\n"]
            for s in bond_signals:
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s["severity"], "•")
                bd_lines.append(f"{icon} 【{s['name']}】\n  {s['narrative']}")
            report += "\n".join(bd_lines)

        sentiment_data = data.get("sentiment") or {}
        sent_signals = st.analyze_sentiment_signals(sentiment_data)
        if sent_signals:
            sent_lines = ["\n━━━━━━━━━━━━━━━\n🧠 情绪极端信号\n"]
            for s in sent_signals:
                icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s["severity"], "•")
                sent_lines.append(f"{icon} 【{s['name']}】\n  {s['narrative']}")
            report += "\n".join(sent_lines)

        # P2-1: 板块资金流信号
        sector_items = data.get("sector_flow") or []
        sector_signals = sf.analyze_sector_rotation(sector_items)
        if sector_signals:
            report += "\n\n" + sf.format_sector_signals(sector_signals)

        # P2-2: 地缘事件
        geo_events = data.get("geo_events") or []
        if geo_events:
            report += "\n\n" + geo.format_geo_brief(geo_events, top=8)

        # W2: AH 溢价套利监控
        try:
            ah_results = ah.fetch_ah_premium()
            if ah_results:
                report += "\n\n━━━━━━━━━━━━━━━\n" + ah.format_summary(ah_results, top_n=20)
                ah_signals = ah.get_signals(ah_results, verify_rare=True)
                if ah_signals:
                    report += "\n\n" + ah.format_signals(ah_signals)
        except Exception as e:
            self.log(f"[evening] AH 溢价监控异常：{e}")

        # W3: ETF 折溢价监控
        try:
            etf_results = etf.fetch_etf_premium()
            if etf_results:
                report += "\n\n━━━━━━━━━━━━━━━\n" + etf.format_summary(etf_results, top_n=20)
                etf_signals = etf.get_signals(etf_results, verify_rare=True)
                if etf_signals:
                    report += "\n\n" + etf.format_signals(etf_signals)
        except Exception as e:
            self.log(f"[evening] ETF 折溢价监控异常：{e}")

        # W4: 指数估值分位监控（盘后快照 + 极端信号 + 一致性告警）
        try:
            iv_records = iv.fetch_and_snapshot()
            if iv_records:
                report += "\n\n━━━━━━━━━━━━━━━\n" + iv.format_summary(iv_records)
                iv_signals = iv.get_signals(iv_records)
                iv_warnings = iv.cross_check(iv_records)
                sig_txt = iv.format_signals(iv_signals, iv_warnings)
                if sig_txt:
                    report += "\n\n" + sig_txt
        except Exception as e:
            self.log(f"[evening] 指数估值分位监控异常：{e}")

        # AI 分析
        prompt = self._build_ai_prompt(data, signals)
        analysis = ai_chat(prompt, temperature=0.7, max_tokens=1400)

        if analysis:
            report += f"\n\n━━━━━━━━━━━━━━━\n🤖 AI 市场解读\n\n{analysis}"
        else:
            report += "\n\n(AI 分析暂不可用)"

        # 每日教学锦囊(轮换)
        report += f"\n\n━━━━━━━━━━━━━━━\n{get_daily_tip()}"

        # P3-1: 仓位健康度（在前瞻性清单之前、教学锦囊之后）
        health = data.get("position_health")
        if health:
            report += "\n\n━━━━━━━━━━━━━━━\n" + pos_trk.format_health_report(health)

        # 前瞻性观察清单（明日关注）
        try:
            watchlist = lookahead.build_tomorrow_watchlist(data=data)
            if watchlist:
                report += f"\n\n{watchlist}"
        except Exception as e:
            print(f"[evening] 前瞻性清单生成失败: {e}")

        report += "\n\n(数据:新浪财经/东财 · 分析:AI)"

        if self.send(report):
            self.state.set(daily_key)
            self.state.save()
            self.log(f"✅ 已发送 {self.now_str}")
            return True
        self.log("❌ 发送失败")
        return False
