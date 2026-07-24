#!/usr/bin/env bash
# 微信公众号草稿箱批量推送（三篇）
# 第1篇：全球宏观日报（16:9 封面）
# 第2篇：彭博社发文日报（1:1 封面）
# 第3篇：意见领袖发言日报（1:1 封面，代码生成）
# 每天 08:00 自动推送
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

# 激活 venv
source .venv/bin/activate
VENV_PYTHON="$(pwd)/.venv/bin/python"
SYSTEM_PYTHON="/usr/local/bin/python3"

# ===== 1. 生成三篇文章 Markdown =====
echo "[publish] 生成全球宏观日报..."
MACRO_PATH=$(${VENV_PYTHON} -m market_monitor.monitors.macro_wechat)
echo "[publish] 宏观文章: ${MACRO_PATH}"

echo "[publish] 生成 Bloomberg 日报..."
BLOOMBERG_PATH=$(${VENV_PYTHON} -m market_monitor.monitors.bloomberg_wechat)
echo "[publish] Bloomberg 文章: ${BLOOMBERG_PATH}"

echo "[publish] 生成意见领袖日报..."
VOICE_PATH=$(${VENV_PYTHON} -m market_monitor.monitors.voice_wechat)
echo "[publish] 意见领袖文章: ${VOICE_PATH}"

# 有效性检查
if [ -z "${MACRO_PATH}" ] || [ ! -f "${MACRO_PATH}" ]; then
    echo "[publish] 宏观文章生成失败，跳过"
    MACRO_PATH=""
fi
if [ -z "${BLOOMBERG_PATH}" ] || [ ! -f "${BLOOMBERG_PATH}" ]; then
    echo "[publish] Bloomberg 文章生成失败，跳过"
    BLOOMBERG_PATH=""
fi
if [ -z "${VOICE_PATH}" ] || [ ! -f "${VOICE_PATH}" ]; then
    echo "[publish] 意见领袖文章生成失败，跳过"
    VOICE_PATH=""
fi

if [ -z "${MACRO_PATH}" ] && [ -z "${BLOOMBERG_PATH}" ] && [ -z "${VOICE_PATH}" ]; then
    echo "[publish] 所有文章生成失败，退出"
    exit 0
fi

# ===== 2. 准备封面图（从 SQLite 读取）=====
echo "[publish] 从数据库加载封面 URL..."

# 从 SQLite 读取封面 URL 并导出到环境变量
eval $(${SYSTEM_PYTHON} scripts/get_wechat_covers.py)
echo "[publish] 封面 URL 已加载"

# 全球宏观：16:9 封面（公众号第一篇列表图）
curl -s -L "${MACRO_COVER_16_9}" -o post-to-wechat/macro-cover.png
echo "[publish] 宏观封面 16:9 就绪"

# 彭博缩略图：1:1（第二篇）
curl -s -L "${BLOOMBERG_COVER_1_1}" -o post-to-wechat/bloomberg-thumb-1x1.png
echo "[publish] 彭博封面 1:1 就绪"

# 意见领袖：1:1 缩略图（第三篇封面）+ 16:9 正文开头图
curl -s -L "${VOICE_COVER_1_1}" -o post-to-wechat/voice-thumb-1x1.png
curl -s -L "${VOICE_COVER_16_9}" -o post-to-wechat/voice-cover-16x9.png
echo "[publish] 意见领袖 1:1 缩略图 + 16:9 正文图就绪"

# ===== 3. 渲染所有文章 HTML =====
SKILL_DIR="${HOME}/.openclaw/workspace/skills/baoyu-skills/skills/baoyu-post-to-wechat"

if [ -n "${MACRO_PATH}" ]; then
    echo "[publish] 渲染宏观文章 HTML..."
    MACRO_JSON=$(bun "${SKILL_DIR}/scripts/md-to-wechat.ts" \
        "${MACRO_PATH}" \
        --theme default \
        --color green 2>/dev/null)
    echo "[publish] 宏观 HTML 渲染完成"
fi

if [ -n "${BLOOMBERG_PATH}" ]; then
    echo "[publish] 渲染 Bloomberg 文章 HTML..."
    BLOOMBERG_JSON=$(bun "${SKILL_DIR}/scripts/md-to-wechat.ts" \
        "${BLOOMBERG_PATH}" \
        --theme default \
        --color blue 2>/dev/null)
    echo "[publish] Bloomberg HTML 渲染完成"
fi

if [ -n "${VOICE_PATH}" ]; then
    echo "[publish] 渲染意见领袖文章 HTML..."
    VOICE_JSON=$(bun "${SKILL_DIR}/scripts/md-to-wechat.ts" \
        "${VOICE_PATH}" \
        --theme default \
        --color blue 2>/dev/null)
    echo "[publish] 意见领袖 HTML 渲染完成"
fi

# ===== 4. 组装多文章并推送到草稿箱 =====
echo "[publish] 组装多文章并推送到微信草稿箱..."

APP_ID=$(grep WECHAT_APP_ID ~/.baoyu-skills/.env | cut -d= -f2 | tr -d '"')
APP_SECRET=$(grep WECHAT_APP_SECRET ~/.baoyu-skills/.env | cut -d= -f2 | tr -d '"')

export MACRO_JSON="${MACRO_JSON:-}"
export BLOOMBERG_JSON="${BLOOMBERG_JSON:-}"
export VOICE_JSON="${VOICE_JSON:-}"
export MACRO_COVER="post-to-wechat/macro-cover.png"
export BLOOMBERG_COVER="post-to-wechat/bloomberg-thumb-1x1.png"
export VOICE_COVER="post-to-wechat/voice-thumb-1x1.png"
export VOICE_BODY_COVER="post-to-wechat/voice-cover-16x9.png"
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

async function processArticle(jsonStr, coverPath, accessToken, label, bodyCoverPath = null) {
    const parsed = JSON.parse(jsonStr);
    let html = fs.readFileSync(parsed.htmlPath, "utf-8");

    if (parsed.contentImages && parsed.contentImages.length > 0) {
        for (const img of parsed.contentImages) {
            if (!html.includes(img.placeholder)) continue;
            console.error(`[wechat] [${label}] Uploading body image: ${img.localPath}`);
            const imgUrl = await uploadBodyImage(img.localPath, accessToken);
            const replacement = `<img src="${imgUrl}" style="display: block; width: 100%; margin: 1.5em auto;">`;
            html = html.split(img.placeholder).join(replacement);
        }
    }

    // 意见领袖文章：在正文开头插入 16:9 封面图
    if (bodyCoverPath) {
        console.error(`[wechat] [${label}] Uploading body cover (16:9): ${bodyCoverPath}`);
        const bodyCoverUrl = await uploadBodyImage(bodyCoverPath, accessToken);
        const bodyCoverHtml = `<img src="${bodyCoverUrl}" style="display: block; width: 100%; margin: 0 auto 1.5em auto; border-radius: 8px;">`;
        // 在 h1 标题之后插入
        const h1EndIndex = html.indexOf("</h1>");
        if (h1EndIndex > -1) {
            html = html.slice(0, h1EndIndex + 5) + bodyCoverHtml + html.slice(h1EndIndex + 5);
        } else {
            html = bodyCoverHtml + html;
        }
    }

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

    if (process.env.MACRO_JSON) {
        console.error("[wechat] Article 1: 全球宏观日报...");
        articles.push(await processArticle(
            process.env.MACRO_JSON,
            path.join(PROJECT_DIR, process.env.MACRO_COVER),
            accessToken,
            "Macro"
        ));
    }

    if (process.env.BLOOMBERG_JSON) {
        console.error("[wechat] Article 2: 彭博社发文日报...");
        articles.push(await processArticle(
            process.env.BLOOMBERG_JSON,
            path.join(PROJECT_DIR, process.env.BLOOMBERG_COVER),
            accessToken,
            "Bloomberg"
        ));
    }

    if (process.env.VOICE_JSON) {
        console.error("[wechat] Article 3: 意见领袖发言日报...");
        articles.push(await processArticle(
            process.env.VOICE_JSON,
            path.join(PROJECT_DIR, process.env.VOICE_COVER),
            accessToken,
            "Voice",
            path.join(PROJECT_DIR, process.env.VOICE_BODY_COVER)
        ));
    }

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