#!/usr/bin/env bash
# Bloomberg 日报 → 微信公众号草稿箱
# 每天 08:00 自动推送
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

# 激活 venv
source .venv/bin/activate
VENV_PYTHON="$(pwd)/.venv/bin/python"

# 1. 生成文章 Markdown
echo "[publish] 生成 Bloomberg 日报..."
ARTICLE_PATH=$(${VENV_PYTHON} -m market_monitor.monitors.bloomberg_wechat)
echo "[publish] 文章路径: ${ARTICLE_PATH}"

if [ -z "${ARTICLE_PATH}" ] || [ ! -f "${ARTICLE_PATH}" ]; then
    echo "[publish] 无文章可发布，退出"
    exit 0
fi

# 2. 下载固定封面图
echo "[publish] 下载固定封面图..."
curl -s -L "https://your-cdn.com/bloomberg-cover.jpg" -o post-to-wechat/bloomberg-cover.jpg
echo "[publish] 封面图已就绪: post-to-wechat/bloomberg-cover.jpg"

# 3. 推送到微信草稿箱
SKILL_DIR="${HOME}/.openclaw/workspace/skills/baoyu-skills/skills/baoyu-post-to-wechat"
echo "[publish] 发布到微信草稿箱..."

bun "${SKILL_DIR}/scripts/wechat-api.ts" \
    "${ARTICLE_PATH}" \
    --theme default \
    --color blue \
    --author "AI边用边想" \
    --cover "post-to-wechat/bloomberg-cover.jpg" 2>&1

echo "[publish] ✅ 完成"