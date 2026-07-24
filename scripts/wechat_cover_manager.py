#!/usr/bin/env python3
"""更新微信公众号封面图 URL"""
import sqlite3
import sys
from datetime import datetime

DB_PATH = "data/market.db"


def list_covers():
    """列出所有封面配置"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, article_type, display_name, thumb_url_1x1, cover_url_16x9, aspect_ratio, enabled
        FROM wechat_cover_images
        ORDER BY id
    """)
    rows = cursor.fetchall()
    conn.close()

    print(f"{'ID':<3} {'类型':<12} {'名称':<18} {'比例':<6} {'启用':<4}")
    print("-" * 70)
    for row in rows:
        enabled = "✓" if row["enabled"] else "✗"
        print(f'{row["id"]:<3} {row["article_type"]:<12} {row["display_name"]:<18} {row["aspect_ratio"]:<6} {enabled:<4}')
        if row["thumb_url_1x1"]:
            print(f"      1:1 缩略: {row['thumb_url_1x1']}")
        if row["cover_url_16x9"]:
            print(f"      16:9 封面: {row['cover_url_16x9']}")
        print()


def update_cover(article_type, field, url):
    """更新指定字段的 URL"""
    valid_fields = ["thumb_url_1x1", "cover_url_16x9"]
    if field not in valid_fields:
        print(f"无效字段: {field}")
        print(f"有效字段: {', '.join(valid_fields)}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"""
        UPDATE wechat_cover_images
        SET {field} = ?, updated_at = CURRENT_TIMESTAMP
        WHERE article_type = ?
    """, (url, article_type))
    conn.commit()
    affected = cursor.rowcount
    conn.close()

    if affected > 0:
        print(f"✅ 已更新 {article_type}.{field} = {url}")
    else:
        print(f"❌ 未找到 article_type: {article_type}")


def print_help():
    print("""
微信公众号封面图管理工具

用法:
  python scripts/wechat_cover_manager.py list              # 列出所有封面配置
  python scripts/wechat_cover_manager.py update <类型> <字段> <URL>

示例:
  # 更新意见领袖的 1:1 缩略图
  python scripts/wechat_cover_manager.py update voice thumb_url_1x1 https://xxx.png

  # 更新意见领袖的 16:9 正文图
  python scripts/wechat_cover_manager.py update voice cover_url_16x9 https://xxx.png

可用类型: macro / bloomberg / voice
可用字段: thumb_url_1x1 (1:1缩略图) / cover_url_16x9 (16:9正文封面)
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "list":
        list_covers()
    elif cmd == "update" and len(sys.argv) == 5:
        update_cover(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print_help()
        sys.exit(1)
