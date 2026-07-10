# DS-1 · U.S. Treasury Yield Curve Fallback

**状态**：✅ 已交付（2026-07-10）
**动机**：`bonds.py` 用 Yahoo Finance 4 个符号（^IRX 13周、^FVX 5Y、^TNX 10Y、^TYX 30Y），**缺 2Y**——而 **2Y-10Y 是最经典衰退指标**。目前 code 用 13 周近似，不够准。

## 目标

新建 `market_monitor/core/us_treasury.py`：
1. 拉取美国财政部官方 CSV，得到全曲线（1M/3M/6M/1Y/**2Y**/3Y/5Y/7Y/10Y/20Y/30Y）
2. **作为主源**（官方数据，日频稳定），Yahoo 作为 fallback
3. 补齐 2Y、修正 2Y-10Y 利差

## 数据源

- **接口**：`https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&_format=csv`
- **免费**：无 Key、无频率限制、CSV 格式
- **字段**：`Date, 1 Mo, 1.5 Month, 2 Mo, 3 Mo, 4 Mo, 6 Mo, 1 Yr, 2 Yr, 3 Yr, 5 Yr, 7 Yr, 10 Yr, 20 Yr, 30 Yr`
- **示例**：`07/09/2026,3.72,...,4.16(2Y),...,4.54(10Y),...`

## 模块设计

```python
def fetch_yield_curve() -> dict:
    """返回今日各期限收益率
    {
      "1M": 3.72, "3M": 3.83, "6M": 3.96, "1Y": 4.02,
      "2Y": 4.16, "3Y": 4.18, "5Y": 4.27, "7Y": 4.40,
      "10Y": 4.54, "20Y": 5.06, "30Y": 5.05,
      "date": date(2026, 7, 9),
      "source": "us_treasury"
    }
    """

def get_key_spreads(curve) -> dict:
    """
    {
      "2Y-10Y": bp,   # 经典衰退指标
      "3M-10Y": bp,   # 美联储偏爱的指标
      "5Y-30Y": bp,
      "inverted_2y10y": bool,
      "inverted_3m10y": bool,
    }
    """
```

## 接入 `bonds.py`

`fetch_bonds()` 逻辑改为：
1. 先调 `us_treasury.fetch_yield_curve()`（主）
2. 失败或缺字段 → 降级到 Yahoo
3. 输出保持向后兼容（沿用 `美债10Y` 等键名）

## 缓存策略

日频数据无需高频拉，加**1 小时内存缓存**避免每次重复下载。

## 已知风险

- [x] Treasury.gov 偶发慢或 5xx → 加 2 次重试
- [x] CSV 格式如果 Treasury 改版会挂 → 加字段存在性校验
- [x] 周末/假日无新数据 → 用最新一天

## 测试计划与结果

### 测试项

- [x] 拉当年全量 CSV
- [x] 校验 2Y、3Y、7Y、10Y、20Y 字段存在
- [x] 校验利差计算正确（2Y-10Y / 3M-10Y / 5Y-30Y）
- [x] `bonds.py` 端到端跑通并且 2Y 出现在报告里
- [x] `analyze_yield_curve` 阈值切换为 bp 口径
- [x] `morning.py` / `evening.py` import 不炋

### 实盘结果（2026-07-09）

**曲线快照**（五档主展示）：

| 期限 | 收益率 | 日变 (bp) |
| ---- | ------ | --------- |
| 3M   | 3.830% | -4.0 |
| **2Y**   | **4.160%** | **-5.0** |
| 5Y   | 4.270% | -4.0 |
| 10Y  | 4.540% | -2.0 |
| 30Y  | 5.050% | -1.0 |

**关键利差**：

| 利差 | 值 | 含义 |
| ---- | --- | ---- |
| **2Y-10Y** | **+38.0 bp** | 未倒挂（经典衰退指标） |
| **3M-10Y** | **+71.0 bp** | 未倒挂（美联储偏爱指标） |
| 5Y-10Y | +27.0 bp | 中长端利差 |
| 5Y-30Y | +78.0 bp | 长端相对陡峭 |

**信号判定**：`analyze_yield_curve()` 返回 `[]`（当日无异常事件，符合预期）。

### 修复的 bug

- **BUG-1**：`analyze_yield_curve` 阈值旧口径 `tnx_pct >= 2.0`（Yahoo % 变化）→ us_treasury 下变为 bp，一切正常日变化都触不到→ 改为 ±10 bp 判定
- **BUG-2**：`format_bonds` 循环 `["13周-10Y", "5Y-10Y", "5Y-30Y"]` 不包含 2Y-10Y → 加 `2Y-10Y` 和 `3M-10Y`
- **BUG-3**：同上 `bonds_summary_for_ai` 也漏→ 同步修复

## Review 建议路径

**给外部 code reviewer（Claude Code / Codex / Cursor）**：

### 优先审查

1. **`market_monitor/core/us_treasury.py`**（5194 bytes）
   - `_fetch_year_csv()` 重试逐降（sleep 1s / 2s）是否够用
   - 内存缓存 1 小时是否合理（日频数据）
   - CSV 字段映射 `_COL_MAP` 完整性
   - 跨年 fallback 逻辑（元旦附近）

2. **`market_monitor/core/bonds.py`**（修改后）
   - 主源 us_treasury → Yahoo 降级逻辑（任一路径失败都不该报错）
   - `calc_spreads()` 在 2Y 存在时不用 13周 近似
   - `inverted` 优先看 2Y-10Y，fallback 13周-10Y
   - `analyze_yield_curve()` bp 阈值与旧 pct 阈值的当量关系（10 bp ≈ 旧 2%）

### 关注点

- ✅ 无 API Key 依赖，User-Agent 已设置
- ✅ 向后兼容：旧字段名称（美债10Y 、 美债5Y 、 美债30Y）保留
- ✅ `pct` 字段强制为 `change_bp / 100`，与 Yahoo 口径对齐
- ⚠️ **13周≠ 3个月**：Yahoo `^IRX` 是 13 周（4 周/月 ≈ 3M），Treasury `3M` 是 91 天，短短几天差异忘不得
- ⚠️ **U.S. Treasury 不包含当日的价格变化 %，只有绝对收益率**：日变化需与前日相减手算（`get_curve_with_changes()` 已处理）

### 建议改进方向

- [ ] 监控数据源健康：连续 2 天拉不到→ 预警
- [ ] 支持 fetch 历史 30 天→ 接入 macro/econ_calendar 做收益率走势图
- [ ] Yahoo 降级时 log warning → 推送告警
- [ ] 兼容 `bonds_summary_for_ai` 新增 2Y-10Y 后，AI 提示词里添加衰退指标解读

### 测试建议

- 单元测试：`get_key_spreads()`、`_fetch_year_csv()` 可 mock CSV
- 集成测试：断网时 `bonds.py` 能降级到 Yahoo（要 mock requests）
- 回归测试：连续跑 5 个工作日，确保无缓存污染、无重复拉取
