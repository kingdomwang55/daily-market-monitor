#!/usr/bin/env bash
# 全球宏观日报 + Bloomberg 日报 -> 微信公众号草稿箱（多文章一次推送）
# 封面配置：
#   - 第一篇（全球宏观）缩略图：16:9（公众号列表）
#   - 第一篇正文开头：16:9
#   - 第二篇（彭博）缩略图：1:1
#   - 第二篇正文开头：16:9
# 每天 08:00 自动推送
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

# 激活 venv
source .venv/bin/activate
VENV_PYTHON="$(pwd)/.venv/bin/python"

# ===== 1. 生成两篇文章 Markdown =====
echo "[publish] 生成全球宏观日报..."
MACRO_PATH=$(${VENV_PYTHON} -m market_monitor.monitors.macro_wechat)
echo "[publish] 宏观文章: ${MACRO_PATH}"

echo "[publish] 生成 Bloomberg 日报..."
BLOOMBERG_PATH=$(${VENV_PYTHON} -m market_monitor.monitors.bloomberg_wechat)
echo "[publish] Bloomberg 文章: ${BLOOMBERG_PATH}"

if [ -z "${MACRO_PATH}" ] || [ ! -f "${MACRO_PATH}" ]; then
    echo "[publish] 宏观文章生成失败，只推 Bloomberg"
    MACRO_PATH=""
fi
if [ -z "${BLOOMBERG_PATH}" ] || [ ! -f "${BLOOMBERG_PATH}" ]; then
    echo "[publish] Bloomberg 文章生成失败，退出"
    exit 0
fi

# ===== 2. 下载封面图 =====
echo "[publish] 下载封面图..."

# 全球宏观：16:9 封面（公众号列表缩略图 + 正文开头）
MACRO_COVER_16_9="https://your-cdn.com/macro-cover.png"
curl -s -L "${MACRO_COVER_16_9}" -o post-to-wechat/macro-cover.png
echo "[publish] 宏观封面 16:9 就绪"

# 彭博缩略图：1:1（公众号第二篇缩略图）
BLOOMBERG_COVER_1_1="https://your-cdn.com/bloomberg-thumb.png"
curl -s -L "${BLOOMBERG_COVER_1_1}" -o post-to-wechat/bloomberg-thumb-1x1.png
echo "[publish] 彭博缩略图 1:1 就绪"

# ===== 3. 渲染两篇文章 HTML =====
SKILL_DIR="${HOME}/.openclaw/workspace/skills/baoyu-skills/skills/baoyu-post-to-wechat"

if [ -n "${MACRO_PATH}" ]; then
    echo "[publish] 渲染宏观文章 HTML..."
    MACRO_JSON=$(bun "${SKILL_DIR}/scripts/md-to-wechat.ts" \
        "${MACRO_PATH}" \
        --theme default \
        --color green 2>/dev/null)
    echo "[publish] 宏观 HTML 渲染完成"
fi

echo "[publish] 渲染 Bloomberg 文章 HTML..."
BLOOMBERG_JSON=$(bun "${SKILL_DIR}/scripts/md-to-wechat.ts" \
    "${BLOOMBERG_PATH}" \
    --theme default \
    --color blue 2>/dev/null)
echo "[publish] Bloomberg HTML 渲染完成"

# ===== 4. 用 Node 脚本组装多文章并推送 =====
echo "[publish] 组装多文章并推送到微信草稿箱..."

# 读取凭证
APP_ID=$(grep WECHAT_APP_ID ~/.baoyu-skills/.env | cut -d= -f2 | tr -d '"')
APP_SECRET=$(grep WECHAT_APP_SECRET ~/.baoyu-skills/.env | cut -d= -f2 | tr -d '"')

# 导出变量给 Node 脚本
export BLOOMBERG_JSON
export MACRO_JSON="${MACRO_JSON:-}"
export MACRO_COVER="post-to-wechat/macro-cover.png"         # 16:9（第一篇缩略图）
export BLOOMBERG_COVER="post-to-wechat/bloomberg-thumb-1x1.png"  # 1:1（第二篇缩略图）
export APP_ID
export APP_SECRET
export PROJECT_DIR
export SKILL_DIR

node -e '
const fs = require("fs");
const path = require("path");

const APP_ID = process.env.APP_ID;
const APP_SECRET = process.env.APP_SECRET;
const PROJECT_DIR = process.env.PROJECT_DIR;

// 微信 API
const DRAFT_URL = "https://api.weixin.qq.com/cgi-bin/draft/add";
const TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token";

async function fetchJson(url, options = {}) {
    const res = await fetch(url, options);
    return res.json();
}

async function fetchAccessToken() {
    const url = `${TOKEN_URL}?grant_type=client_credential&appid=${APP_ID}&secret=${APP_SECRET}`;
    const data = await fetchJson(url);
    if (!data.access_token) throw new Error(`Token failed: ${JSON.stringify(data)}`);
    return data.access_token;
}

async function uploadImage(imagePath, accessToken) {
    const url = `https://api.weixin.qq.com/cgi-bin/material/add_material?access_token=${accessToken}&type=image`;
    const formData = new FormData();
    const buffer = fs.readFileSync(imagePath);
    const ext = path.extname(imagePath).slice(1) || "png";
    formData.append("media", new Blob([buffer]), `cover.${ext}`);
    const res = await fetch(url, { method: "POST", body: formData });
    const data = await res.json();
    if (!data.media_id) throw new Error(`Upload failed: ${JSON.stringify(data)}`);
    return data;
}

async function uploadBodyImage(imagePath, accessToken) {
    const url = `https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token=${accessToken}`;
    const formData = new FormData();
    const buffer = fs.readFileSync(imagePath);
    const ext = path.extname(imagePath).slice(1) || "png";
    formData.append("media", new Blob([buffer]), `body.${ext}`);
    const res = await fetch(url, { method: "POST", body: formData });
    const data = await res.json();
    if (!data.url) throw new Error(`Body image upload failed: ${JSON.stringify(data)}`);
    return data.url;
}

async function processArticle(jsonStr, coverPath, accessToken, label) {
    const parsed = JSON.parse(jsonStr);
    let html = fs.readFileSync(parsed.htmlPath, "utf-8");

    // 替换正文图片占位符
    if (parsed.contentImages && parsed.contentImages.length > 0) {
        for (const img of parsed.contentImages) {
            if (!html.includes(img.placeholder)) continue;
            console.error(`[wechat] [${label}] Uploading body image: ${img.localPath}`);
            const imgUrl = await uploadBodyImage(img.localPath, accessToken);
            const replacement = `<img src="${imgUrl}" style="display: block; width: 100%; margin: 1.5em auto;">`;
            html = html.split(img.placeholder).join(replacement);
        }
    }

    // 上传缩略图封面
    console.error(`[wechat] [${label}] Uploading thumb cover: ${coverPath}`);
    const coverResp = await uploadImage(coverPath, accessToken);
    console.error(`[wechat] [${label}] Cover uploaded: ${coverResp.media_id}`);

    return {
        article_type: "news",
        title: parsed.title,
        content: html,
        thumb_media_id: coverResp.media_id,
        author: parsed.author || "AI边用边想",
        digest: parsed.summary || "",
    };
}

async function main() {
    console.error("[wechat] Fetching access token...");
    const accessToken = await fetchAccessToken();

    const articles = [];

    // 第一篇：全球宏观（16:9 缩略图）
    if (process.env.MACRO_JSON) {
        console.error("[wechat] Processing article 1: 全球宏观日报...");
        const article1 = await processArticle(
            process.env.MACRO_JSON,
            path.join(PROJECT_DIR, process.env.MACRO_COVER),
            accessToken,
            "Macro"
        );
        articles.push(article1);
    }

    // 第二篇：彭博（1:1 缩略图）
    console.error("[wechat] Processing article 2: 彭博社发文日报...");
    const article2 = await processArticle(
        process.env.BLOOMBERG_JSON,
        path.join(PROJECT_DIR, process.env.BLOOMBERG_COVER),
        accessToken,
        "Bloomberg"
    );
    articles.push(article2);

    // 推送到草稿箱
    console.error(`[wechat] Publishing ${articles.length} articles to draft...`);
    const res = await fetch(`${DRAFT_URL}?access_token=${accessToken}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ articles }),
    });
    const data = await res.json();
    if (data.errcode && data.errcode !== 0) {
        throw new Error(`Publish failed ${data.errcode}: ${data.errmsg}`);
    }
    console.log(JSON.stringify({ success: true, media_id: data.media_id, articleCount: articles.length }, null, 2));
    console.error(`[wechat] Published successfully! media_id: ${data.media_id} (${articles.length} articles)`);
}

main().catch(err => {
    console.error(`[wechat] Error: ${err.message}`);
    process.exit(1);
});
' 2>&1

echo "[publish] ✅ 完成"
