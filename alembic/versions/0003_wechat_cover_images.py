"""Add wechat cover images table.

Revision ID: 0003_wechat_cover_images
Revises: 0002_signal_notes
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_wechat_cover_images"
down_revision = "0002_signal_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wechat_cover_images",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("article_type", sa.String(32), nullable=False, unique=True, index=True),  # macro/bloomberg/voice
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("thumb_url_1x1", sa.String(512)),  # 1:1 缩略图（公众号列表封面）
        sa.Column("cover_url_16x9", sa.String(512)),  # 16:9 正文封面图
        sa.Column("aspect_ratio", sa.String(16), default="16:9"),  # 默认封面比例
        sa.Column("enabled", sa.Boolean, default=True, nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )

    # 插入初始数据
    op.execute("""
    INSERT INTO wechat_cover_images
    (article_type, display_name, thumb_url_1x1, cover_url_16x9, aspect_ratio, enabled, updated_at, created_at)
    VALUES
    ('macro', '全球宏观日报', 'https://your-cdn.com/macro-thumb.png', 'https://your-cdn.com/macro-cover.png', '16:9', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('bloomberg', '彭博社发文日报', 'https://your-cdn.com/bloomberg-thumb.png', 'https://your-cdn.com/bloomberg-cover.png', '1:1', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('voice', '意见领袖发言日报', 'https://your-cdn.com/voice-thumb.png', 'https://your-cdn.com/voice-cover.png', '1:1', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """)


def downgrade() -> None:
    op.drop_table("wechat_cover_images")
