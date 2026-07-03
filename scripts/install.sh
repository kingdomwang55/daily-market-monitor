#!/usr/bin/env bash
# 安装 launchd 任务（不影响老的 com.openclaw.* 任务）
set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCHD_DIR="$PROJECT_ROOT/launchd"
DEST="$HOME/Library/LaunchAgents"

echo "🐉 market-monitor 安装 launchd 任务"
echo "源目录: $LAUNCHD_DIR"
echo "目标: $DEST"
echo ""

# 1. 生成最新 plist
python3 "$PROJECT_ROOT/scripts/gen_launchd.py"
echo ""

# 2. 复制到 LaunchAgents
for f in "$LAUNCHD_DIR"/*.plist; do
    name=$(basename "$f")
    echo "→ 安装 $name"
    cp "$f" "$DEST/$name"
    # 卸载旧的（如果有）
    launchctl unload "$DEST/$name" 2>/dev/null || true
    launchctl load "$DEST/$name"
done

echo ""
echo "✅ 安装完成。查看当前任务："
launchctl list | grep market-monitor
