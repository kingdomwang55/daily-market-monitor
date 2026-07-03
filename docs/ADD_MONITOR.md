# 如何添加新监控

## 3 步添加一个新监控

### 1. 写 Monitor 类

在 `market_monitor/monitors/` 新建文件，例如 `btc.py`:

```python
from ..core.base import BaseMonitor
from ..core import data_source as ds


class BtcMonitor(BaseMonitor):
    name = "btc"
    display_name = "BTC 监控"

    def run(self) -> bool:
        # 1. 读配置
        threshold = self.config.get("btc.alert_pct", 5.0)

        # 2. 拉数据
        # ... 你的取数逻辑

        # 3. 判断是否触发
        if not triggered:
            self.log(f"{self.now_str} BTC 平稳")
            return True

        # 4. 组装消息
        message = f"🪙 BTC 异动 ({self.now_str})\n..."

        # 5. 发送 + 保存状态
        if self.send(message):
            self.state.save()
            return True
        return False
```

### 2. 在 registry 注册

编辑 `market_monitor/monitors/registry.py`:

```python
from .btc import BtcMonitor

REGISTRY = {
    m.name: m for m in [
        # ...
        BtcMonitor,
    ]
}
```

### 3. 在 config 加配置

编辑 `config/config.yaml`:

```yaml
btc:
  enabled: true
  alert_pct: 5.0
  symbols: [BTC, ETH]
```

### 4. 测试

```bash
python -m market_monitor.cli run btc --force
```

### 5. （可选）加 launchd 任务

编辑 `scripts/gen_launchd.py`，添加：

```python
schedule = make_interval_schedule(3600)  # 每小时
(LAUNCHD_DIR / "com.market-monitor.btc.plist").write_text(
    build_plist_via_module("com.market-monitor.btc", "btc", schedule)
)
```

然后重新安装：
```bash
bash scripts/install.sh
```

---

## BaseMonitor 提供的能力

| 属性/方法 | 说明 |
|---|---|
| `self.config` | 全局配置（`.get('path.to.value')`） |
| `self.state` | 状态存储（防重复推送） |
| `self.force` | 是否强制模式 |
| `self.snapshot` | 是否快照模式 |
| `self.now` / `self.now_str` / `self.today` | 时间 |
| `self.log(msg)` | 打印日志（stderr） |
| `self.send(msg)` | 发送飞书消息 |
| `self.emoji_by_pct(pct)` | 根据涨跌幅返回 emoji |

## State 使用

```python
# 检查是否已处理
if not self.state.has(f"alert_{code}_{today}"):
    # 触发
    self.state.set(f"alert_{code}_{today}")
    
# 记得最后 save
self.state.save()
```
