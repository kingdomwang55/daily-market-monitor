/* ==========================================================================
   微信公众号封面图管理表 - 初始化脚本
   数据库: SQLite 3.x
   
   说明:
     - 该表存储三篇微信文章的封面图 URL 配置
     - 从数据库读取便于管理、历史追踪、统一更新
     - 脚本为脱敏版，URL 已替换为示例占位符
   ========================================================================== */

-- 创建表
CREATE TABLE IF NOT EXISTS wechat_cover_images (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    article_type    VARCHAR(32)    NOT NULL UNIQUE,  -- 文章标识: macro / bloomberg / voice
    display_name    VARCHAR(128)   NOT NULL,          -- 显示名称（人读）
    thumb_url_1x1   VARCHAR(512),                     -- 1:1 正方形缩略图（公众号列表封面）
    cover_url_16x9  VARCHAR(512),                     -- 16:9 宽屏封面（文章正文开头）
    aspect_ratio    VARCHAR(16)    DEFAULT '16:9',    -- 公众号列表封面的默认比例
    enabled         BOOLEAN        DEFAULT 1,         -- 是否启用（0=禁用, 1=启用）
    notes           TEXT,                             -- 备注说明
    updated_at      DATETIME       NOT NULL,          -- 最后更新时间
    created_at      DATETIME       NOT NULL           -- 创建时间
);

-- 索引（按文章类型快速查询）
CREATE INDEX IF NOT EXISTS idx_wechat_cover_article ON wechat_cover_images(article_type);

/* ==========================================================================
   初始数据（脱敏示例，实际部署时替换为真实 URL）
   ========================================================================== */

INSERT INTO wechat_cover_images
(article_type, display_name, thumb_url_1x1, cover_url_16x9, aspect_ratio, enabled, notes, updated_at, created_at)
VALUES
-- 第1篇: 全球宏观日报
-- 说明: 公众号首篇文章，用 16:9 大图撑满整个列表宽度
(
    'macro',
    '全球宏观日报',
    NULL,                                      -- 第1篇不需要 1:1 缩略
    'https://your-cdn.com/macro-cover.png',    -- 16:9 封面图（替换为真实 URL）
    '16:9',
    1,
    '公众号首篇，16:9 宽屏封面',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
),

-- 第2篇: 彭博社发文日报
-- 说明: 第二篇及后续文章，公众号列表展示 1:1 正方形缩略图
(
    'bloomberg',
    '彭博社发文日报',
    'https://your-cdn.com/bloomberg-thumb.png', -- 1:1 缩略图（替换为真实 URL）
    NULL,                                       -- 彭博文章正文不需要额外封面
    '1:1',
    1,
    '第二篇，1:1 正方形缩略图 + 代码生成头图',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
),

-- 第3篇: 意见领袖发言日报
-- 说明: 第三篇，公众号列表用 1:1 缩略，文章正文开头插 16:9 封面
(
    'voice',
    '意见领袖发言日报',
    'https://your-cdn.com/voice-thumb.png',     -- 1:1 缩略图（替换为真实 URL）
    'https://your-cdn.com/voice-cover.png',     -- 16:9 正文开头图（替换为真实 URL）
    '1:1',
    1,
    '第三篇，双图配置：1:1缩略 + 16:9正文头图',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);

/* ==========================================================================
   字段说明对照表

   article_type    | 含义                    | thumb_url_1x1 | cover_url_16x9
   ----------------|-------------------------|---------------|----------------
   macro           | 全球宏观日报（第1篇）   | 不需要        | 需要 16:9
   bloomberg       | 彭博社发文日报（第2篇） | 需要 1:1      | 不需要
   voice           | 意见领袖发言日报（第3篇）| 需要 1:1      | 需要 16:9

   使用示例 SQL:

   -- 查询所有启用的封面配置
   SELECT article_type, display_name, thumb_url_1x1, cover_url_16x9
   FROM wechat_cover_images
   WHERE enabled = 1;

   -- 更新意见领袖的 16:9 封面图
   UPDATE wechat_cover_images
   SET cover_url_16x9 = 'https://new-url.png', updated_at = CURRENT_TIMESTAMP
   WHERE article_type = 'voice';
   ========================================================================== */
