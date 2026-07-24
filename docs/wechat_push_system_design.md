# 微信公众号推送系统 - 程序设计文档

## 一、系统概述

### 1.1 设计目标

自动化生成三篇高质量微信公众号文章，并推送到草稿箱，形成"每日早上8点三条内容连发"的固定推送模式。

### 1.2 推送内容

| 顺序 | 文章类型 | 微信列表封面 | 文章正文头图 |
|------|----------|-------------|-------------|
| 第1篇 | 全球宏观日报 | 16:9 宽屏大图 | 16:9 封面图（从 DB 读取） |
| 第2篇 | 彭博社发文日报 | 1:1 正方形缩略 | 16:9 封面图（从 DB 读取） |
| 第3篇 | 意见领袖发言日报 | 1:1 正方形缩略 | 16:9 封面图（从 DB 读取） |

### 1.3 触发方式

- **定时推送**：`launchd` 每天 08:00 自动执行 `publish_multi_wechat.sh`
- **手动推送**：直接运行脚本 `./scripts/publish_multi_wechat.sh`

---

## 二、整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                     publish_multi_wechat.sh                   │
│                          （主入口）                            │
├──────────────┬───────────────┬───────────────────────────────┤
│  Step1       │  Step2        │  Step3                        │
│  生成3篇MD   │  下载封面图   │  渲染HTML + 推送草稿箱        │
└──────────────┴───────────────┴───────────────────────────────┘
         │              │                    │
         ▼              ▼                    ▼
┌──────────────┐  ┌──────────┐       ┌──────────────┐
│ macro_wechat │  │  SQLite  │       │ wechat API   │
│ bloomberg_wechat │  数据库  │       │ (add_draft)  │
│ voice_wechat   │  读取URL  │       └──────────────┘
└──────────────┘  └──────────┘
```

---

## 三、文件结构

```
market-monitor/
├── market_monitor/
│   ├── monitors/
│   │   ├── macro_wechat.py          # 全球宏观日报生成器
│   │   ├── bloomberg_wechat.py      # 彭博社发文日报生成器
│   │   └── voice_wechat.py          # 意见领袖发言日报生成器
│   └── core/
│       └── cover_utils.py           # 封面图 URL 读取工具（从 SQLite）
│
├── scripts/
│   ├── publish_multi_wechat.sh     # ✅ 主入口：三篇连发推送脚本
│   ├── publish_bloomberg_wechat.sh  # 旧版：单篇彭博推送（仍从 DB 读取 URL）
│   ├── get_wechat_covers.py         # 从 SQLite 读取封面 URL（shell 调用）
│   ├── wechat_cover_manager.py      # 封面 URL 管理工具(list/update)
│   └── gen_voice_cover.py           # （废弃）旧版代码生成意见领袖封面
│
├── sql/
│   ├── README.md                    # SQL 脚本说明 + 数据字典
│   └── wechat_cover_images_init.sql # 封面图配置表初始化（脱敏）
│
└── post-to-wechat/                  # 运行时目录（gitignore）
    ├── macro-cover.png              # 运行时下载的封面图
    ├── bloomberg-thumb-1x1.png
    ├── voice-thumb-1x1.png
    └── voice-cover-16x9.png
```

---

## 四、数据库设计

### 4.1 表结构：`wechat_cover_images`

存储三篇文章的封面图 URL 配置。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键，自增 |
| `article_type` | VARCHAR(32) | 文章唯一标识：`macro` / `bloomberg` / `voice` |
| `display_name` | VARCHAR(128) | 显示名称 |
| `thumb_url_1x1` | VARCHAR(512) | 1:1 正方形缩略图（公众号列表封面） |
| `cover_url_16x9` | VARCHAR(512) | 16:9 宽屏封面（文章正文开头） |
| `aspect_ratio` | VARCHAR(16) | 公众号列表封面的默认比例 |
| `enabled` | BOOLEAN | 是否启用 |
| `notes` | TEXT | 备注 |
| `updated_at` | DATETIME | 最后更新时间 |
| `created_at` | DATETIME | 创建时间 |

### 4.2 当前数据

| article_type | thumb_url_1x1 (1:1) | cover_url_16x9 (16:9) |
|--------------|---------------------|----------------------|
| `macro` | ✅ `p08ldjdxuf.png` | ✅ `l66nijvvvp.png` |
| `bloomberg` | ✅ `3uoqbml7zt.png` | ✅ `g8poxfvmml.jpg` |
| `voice` | ✅ `vmg34p0a1k.png` | ✅ `il2cyqui9i.png` |

---

## 五、核心流程详解

### 5.1 主脚本：`publish_multi_wechat.sh`

执行流程：

```
1. 激活 venv 环境
   │
   ▼
2. 生成三篇文章的 Markdown
   ├─ macro_wechat     → post-to-wechat/YYYY-MM-DD/macro-daily.md
   ├─ bloomberg_wechat → post-to-wechat/YYYY-MM-DD/bloomberg-daily.md
   └─ voice_wechat     → post-to-wechat/YYYY-MM-DD/voice-daily.md
   │
   ▼
3. 从 SQLite 读取封面 URL
   └─ python3 scripts/get_wechat_covers.py
      输出环境变量格式：MACRO_COVER_16_9="xxx" BLOOMBERG_COVER_1_1="xxx" ...
   │
   ▼
4. 下载封面图到本地
   ├─ curl macro 16:9     → post-to-wechat/macro-cover.png
   ├─ curl bloomberg 1:1  → post-to-wechat/bloomberg-thumb-1x1.png
   ├─ curl voice 1:1      → post-to-wechat/voice-thumb-1x1.png
   └─ curl voice 16:9     → post-to-wechat/voice-cover-16x9.png
   │
   ▼
5. 调用 md-to-wechat.ts 渲染 HTML
   └─ baoyu-skills 的 Markdown → 微信 HTML 转换器
      处理图片、字体、颜色、样式等微信兼容问题
   │
   ▼
6. Node.js 调用微信 API 上传草稿
   ├─ 6.1 获取 access_token (client_credential 模式)
   ├─ 6.2 form-data 上传封面图获取 media_id
   ├─ 6.3 上传正文内图片获取 URL
   └─ 6.4 组装 articles 数组，调用 add_draft 接口
   │
   ▼
7. 完成，输出 media_id
```

### 5.2 文章生成器：`xxx_wechat.py`

**通用结构**（三篇生成器遵循相同模式）：

```python
def main():
    # 1. 拉取原始数据
    items = fetch_data()
    
    # 2. AI 分析生成内容
    prompt = build_prompt(items)
    content = ai_chat(prompt, temperature=0.5, max_tokens=4000)
    
    # 3. 合规风控过滤
    content = compliance_filter(content)
    
    # 4. 组装完整 Markdown
    md = f"""---
title: "标题"
summary: "{extract_summary(content)}"
author: AI边用边想
date: {today}
---

# 文章标题

{content}

---

# 📚 每日锦囊

{daily_tip}

---

*本文由 AI 基于公开信息自动生成...*
"""
    # 5. 写入文件，输出文件路径
    print(out_path)
```

### 5.3 封面图 URL 读取机制

所有封面图 URL 统一存储在 SQLite `wechat_cover_images` 表中，代码通过统一接口读取：

```python
# market_monitor/core/cover_utils.py
from market_monitor.core.cover_utils import get_cover_url

# Python 代码中调用
cover_url = get_cover_url("bloomberg", "16x9")   # 16:9 正文头图
thumb_url = get_cover_url("bloomberg", "1x1")     # 1:1 缩略图
```

```bash
# Shell 脚本中调用（输出环境变量格式）
eval $(python3 scripts/get_wechat_covers.py)
# 或直接内联调用
COVER_URL=$(python3 -c "from market_monitor.core.cover_utils import get_cover_url; print(get_cover_url('bloomberg', '16x9'))")
```

**设计要点**：
- 代码中零硬编码 URL，全部从数据库读取
- 真实 URL 只存在于 `data/market.db`（被 `.gitignore` 排除）
- 迁移脚本和 SQL 初始化脚本使用脱敏占位符

### 5.4 正文开头图片插入逻辑

第三篇（voice）在文章正文开头插入 16:9 封面图：

```javascript
// 第3篇 voice 特殊处理：插入 16:9 头图
if (bodyCoverPath) {
  // 1. 上传图片获取微信内 URL
  const bodyCoverUrl = await uploadBodyImage(bodyCoverPath, accessToken);
  
  // 2. 组装 HTML
  const bodyCoverHtml = `<img src="${bodyCoverUrl}" style="display:block; width:100%; 
                             margin:0 auto 1.5em auto; border-radius:8px;">`;
  
  // 3. 在 <h1> 标题之后插入
  const h1EndIndex = html.indexOf("</h1>");
  if (h1EndIndex > -1) {
    html = html.slice(0, h1EndIndex + 5) + bodyCoverHtml + html.slice(h1EndIndex + 5);
  }
}
```

---

## 六、微信 API 调用细节

### 6.1 认证方式

- **模式**：`client_credential`（公众号第三方平台模式）
- **凭证存储**：`~/.baoyu-skills/.env`
  ```bash
  WECHAT_APP_ID=wx_xxx
  WECHAT_APP_SECRET=xxx
  ```

### 6.2 关键 API 端点

| API | 用途 | 参数 |
|-----|------|------|
| `GET /cgi-bin/token` | 获取 access_token | `grant_type=client_credential` |
| `POST /cgi-bin/material/add_material` | 上传永久素材（封面图用） | `type=image` + form-data |
| `POST /cgi-bin/media/uploadimg` | 上传图文消息内图片 | form-data |
| `POST /cgi-bin/draft/add` | 添加草稿 | `{ articles: [...] }` |

### 6.3 `add_draft` 请求格式

```javascript
{
  "articles": [
    {
      "title": "全球宏观日报",
      "content": "<!DOCTYPE html>...</html>",
      "thumb_media_id": "media_id_xxx",  // 上传封面返回的 media_id
      "author": "AI边用边想",
      "digest": "文章摘要..."
    },
    { /* 第2篇 */ },
    { /* 第3篇 */ }
  ]
}
```

---

## 七、管理工具

### 7.1 `wechat_cover_manager.py`

封面图配置管理工具。

**用法**：
```bash
# 列出所有封面配置
python scripts/wechat_cover_manager.py list

# 更新 voice 的 1:1 缩略图
python scripts/wechat_cover_manager.py update voice thumb_url_1x1 https://xxx.png

# 更新 voice 的 16:9 封面图
python scripts/wechat_cover_manager.py update voice cover_url_16x9 https://xxx.png
```

---

## 八、关键设计决策

### 8.1 封面图存储方式演进

| 阶段 | 存储方式 | 问题 |
|------|---------|------|
| v1 | 硬编码在脚本里 | 改 URL 要改代码，易出错，且会暴露真实 CDN URL |
| v2 | `.env` 配置文件 | 无法追踪历史，无统一管理 |
| v3 ✅ | SQLite 数据库 `wechat_cover_images` + `cover_utils.py` 统一读取 | 统一管理、可审计、代码零硬编码 URL |

### 8.2 封面图生成方式演进

| 阶段 | 生成方式 | 问题 |
|------|---------|------|
| v1 | Python PIL 代码生成封面 | 样式丑，每天重复造轮子 |
| v2 ✅ | CDN 静态图 + AI 设计 | 样式统一、美观、可人工调整 |

### 8.3 为什么第3篇要在正文插 16:9 图

- **公众号列表页**：第二篇/第三篇只显示 1:1 正方形缩略（微信排版限制）
- **文章详情页**：开头一张 16:9 大图更有视觉冲击力，提升点击率
- **视觉一致性**：三篇文章打开后都有统一风格的头图

---

## 九、后续优化方向

- [ ] **封面图自动轮换**：每周/每月自动换一张图，避免用户视觉疲劳
- [ ] **推送结果回调**：推送成功/失败发送通知
- [ ] **发布时间配置**：支持从数据库配置每天几点发布
- [ ] **文章顺序灵活调整**：配置表加 `order` 字段，支持任意排序
- [ ] **AB 测试**：同一篇文章多封面测试点击率
