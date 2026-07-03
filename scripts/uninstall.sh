#!/usr/bin/env bash
# 卸载 launchd 任务
set -e

DEST="$HOME/Library/LaunchAgents"

echo "🐉 market-monitor 卸载 launchd 任务"
for f in "$DEST"/com.market-monitor.*.plist; do
    [ -e "$f" ] || continue
    name=$(basename "$f")
    echo "→ 卸载 $name"
    launchctl unload "$f" 2>/dev/null || true
    rm -f "$f"
done
echo "✅ 卸载完成"
