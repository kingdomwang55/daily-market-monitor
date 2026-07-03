"""数据源解析测试"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from market_monitor.core.data_source import (
    parse_index_simple, parse_stock, parse_us_index, parse_us_stock,
    parse_hk_index, parse_hk_stock,
)


def test_parse_index_simple():
    line = 'var hq_str_s_sh000001="上证指数,4028.36,-83.66,-2.03,3210232,3212341";'
    r = parse_index_simple(line)
    assert r["name"] == "上证指数"
    assert abs(r["close"] - 4028.36) < 0.01
    assert abs(r["pct"] - (-2.03)) < 0.01


def test_parse_us_index():
    line = 'var hq_str_int_dji="道琼斯,46247.29,299.97,0.65";'
    r = parse_us_index(line)
    assert r["name"] == "道琼斯"
    assert r["close"] == 46247.29
    assert r["pct"] == 0.65


def test_parse_us_stock():
    line = 'var hq_str_gb_pdd="拼多多,82.3900,-0.16,2026-07-03";'
    r = parse_us_stock(line)
    assert r["name"] == "拼多多"
    assert r["close"] == 82.39
    assert r["pct"] == -0.16


def test_parse_hk_index():
    line = 'var hq_str_hkHSI="HSI,恒生指数,23055.03,23100.00,23200.00,23000.00,23150.00,95.00,0.41,0,0,0,0,28056.10,22518.00,2026/07/03,15:00";'
    r = parse_hk_index(line)
    assert r["name"] == "恒生指数"
    assert r["close"] == 23150.00
    assert r["pct"] == 0.41


def test_parse_stock_empty():
    """字段为空时不崩"""
    line = 'var hq_str_sh518880="黄金ETF,,,,,,";'
    r = parse_stock(line)
    # 允许 None 或 0 close
    assert r is None or r["close"] == 0


if __name__ == "__main__":
    test_parse_index_simple()
    test_parse_us_index()
    test_parse_us_stock()
    test_parse_hk_index()
    test_parse_stock_empty()
    print("✅ 所有测试通过")
