"""时间工具（数据层专用）

规则：
- 数据库存 UTC naive datetime
- 交易日按 Asia/Shanghai 判定
- 应用层展示时才转回本地时区
"""
from datetime import datetime, date, timezone, timedelta

# Asia/Shanghai = UTC+8
_CN_TZ = timezone(timedelta(hours=8))


def utc_now() -> datetime:
    """当前 UTC naive datetime（存 DB）"""
    return datetime.utcnow()


def to_cn(dt: datetime) -> datetime:
    """UTC naive → Asia/Shanghai naive"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_CN_TZ).replace(tzinfo=None)


def cn_trade_date(dt: datetime = None) -> date:
    """给定 UTC datetime，返回 Asia/Shanghai 的交易日"""
    if dt is None:
        dt = utc_now()
    return to_cn(dt).date()
