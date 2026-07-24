#!/usr/bin/env python3
"""从 SQLite 读取微信公众号封面图 URL"""
import sqlite3
import json
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "market.db")

def get_cover_urls():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT article_type, display_name, thumb_url_1x1, cover_url_16x9, aspect_ratio
        FROM wechat_cover_images
        WHERE enabled = 1
        ORDER BY id
    """)
    rows = cursor.fetchall()
    conn.close()

    result = {}
    for row in rows:
        result[row["article_type"]] = {
            "display_name": row["display_name"],
            "thumb_url_1x1": row["thumb_url_1x1"],
            "cover_url_16x9": row["cover_url_16x9"],
            "aspect_ratio": row["aspect_ratio"],
        }
    return result

if __name__ == "__main__":
    urls = get_cover_urls()
    # 输出为 shell 可解析的格式
    for key, val in urls.items():
        if val["thumb_url_1x1"]:
            print(f'{key.upper()}_COVER_1_1="{val["thumb_url_1x1"]}"')
        if val["cover_url_16x9"]:
            print(f'{key.upper()}_COVER_16_9="{val["cover_url_16x9"]}"')
