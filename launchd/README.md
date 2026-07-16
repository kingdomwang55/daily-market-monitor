# launchd/

本目录用于存放 macOS launchd 任务 plist 文件。

**这些 plist 是本地生成的、含机器路径，不入版本库**（见根目录 `.gitignore`）。

生成方式：

```bash
python scripts/gen_launchd.py
# 或使用一键脚本
bash scripts/install.sh
```

生成后：`.plist` 文件出现在 `launchd/` 下，`install.sh` 会拷贝到
`~/Library/LaunchAgents/` 并 `launchctl load`。

如需自定义 Python 解释器：

```bash
MARKET_MONITOR_PYTHON=/path/to/python bash scripts/install.sh
```
