"""从 SQLite 数据库读取微信公众号封面图 URL"""
import sqlite3
import os

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "market.db")


def _get_conn():
    return sqlite3.connect(_DB_PATH)


def get_cover_url(article_type: str, ratio: str = "16x9") -> str:
    """获取封面图 URL

    Args:
        article_type: macro / bloomberg / voice
        ratio: "16x9" 或 "1x1"

    Returns:
        URL 字符串，找不到则返回空字符串
    """
    field = "cover_url_16x9" if ratio == "16x9" else "thumb_url_1x1"
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {field} FROM wechat_cover_images WHERE article_type = ? AND enabled = 1",
        (article_type,),
    )
    row = cursor.fetchone()
    conn.close()
    return row[0] if row and row[0] else ""
