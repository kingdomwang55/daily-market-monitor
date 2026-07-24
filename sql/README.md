# SQL 脚本目录

本目录存放数据库相关的初始化脚本、DDL 定义和数据字典。

## 脚本说明

| 文件 | 说明 |
|------|------|
| `wechat_cover_images_init.sql` | 微信公众号封面图管理表初始化脚本（脱敏版，带完整注释） |

## 数据库表清单

### wechat_cover_images（微信公众号封面图配置）

存储三篇微信文章的封面图 URL 配置，便于统一管理和更新。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 主键，自增 |
| `article_type` | VARCHAR(32) | 文章唯一标识：`macro` / `bloomberg` / `voice` |
| `display_name` | VARCHAR(128) | 显示名称（人可读） |
| `thumb_url_1x1` | VARCHAR(512) | 1:1 正方形缩略图（公众号列表封面） |
| `cover_url_16x9` | VARCHAR(512) | 16:9 宽屏封面（文章正文开头） |
| `aspect_ratio` | VARCHAR(16) | 公众号列表封面的默认比例 |
| `enabled` | BOOLEAN | 是否启用（0=禁用，1=启用） |
| `notes` | TEXT | 备注说明 |
| `updated_at` | DATETIME | 最后更新时间 |
| `created_at` | DATETIME | 创建时间 |

## 配置对照表

| 文章顺序 | article_type | 名称 | thumb_url_1x1 | cover_url_16x9 |
|----------|--------------|------|---------------|----------------|
| 第1篇 | macro | 全球宏观日报 | ❌ 不需要 | ✅ 需要 16:9 |
| 第2篇 | bloomberg | 彭博社发文日报 | ✅ 需要 1:1 | ❌ 不需要 |
| 第3篇 | voice | 意见领袖发言日报 | ✅ 需要 1:1 | ✅ 需要 16:9 |

## 常用 SQL

```sql
-- 查询所有启用的封面配置
SELECT article_type, display_name, thumb_url_1x1, cover_url_16x9
FROM wechat_cover_images
WHERE enabled = 1;

-- 更新意见领袖的 1:1 缩略图
UPDATE wechat_cover_images
SET thumb_url_1x1 = 'https://new-url.png', updated_at = CURRENT_TIMESTAMP
WHERE article_type = 'voice';
```
