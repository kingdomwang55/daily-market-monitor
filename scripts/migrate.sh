#!/usr/bin/env bash
# 从老的 com.openclaw.* 任务迁移到 com.market-monitor.*
# 步骤：
#   1. 先安装新版本（com.market-monitor.*）
#   2. 手动观察一段时间确认无异常
#   3. 运行本脚本移除旧任务
set -e

DEST="$HOME/Library/LaunchAgents"

OLD_TASKS=(
    "com.openclaw.stabilize-alert"
    "com.openclaw.us-market-alert"
    "com.openclaw.hk-market-alert"
    "com.openclaw.market-shock-alert"
    "com.openclaw.price-alert"
)

echo "🐉 迁移：移除旧 com.openclaw.* 监控任务（保留 stock-morning/stock-evening/health-check）"
echo ""
read -p "确认要移除以上任务吗？(yes/no) " ans
if [ "$ans" != "yes" ]; then
    echo "已取消"
    exit 0
fi

for t in "${OLD_TASKS[@]}"; do
    f="$DEST/$t.plist"
    if [ -f "$f" ]; then
        echo "→ 卸载 $t"
        launchctl unload "$f" 2>/dev/null || true
        # 备份到 /tmp
        mv "$f" "/tmp/$t.plist.bak"
        echo "   已备份到 /tmp/$t.plist.bak"
    fi
done

echo ""
echo "✅ 迁移完成。当前监控任务："
launchctl list | grep -E "market-monitor|openclaw" | grep -v gateway
