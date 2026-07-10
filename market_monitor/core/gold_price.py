"""
金价工具模块 —— 统一美元/盎司与人民币/克的换算与格式化

用户偏好（Steven）：
- 金价一律以 **美元/盎司 (USD/oz)** 为主展示
- 括号备注 **人民币/克 (CNY/g)**

数据源：
- COMEX 黄金主力（纽约黄金）: sina hf_GC —— 美元/盎司
- 现货黄金 XAUUSD:            sina fx_sxauusd —— 美元/盎司（备用）
- 沪金主力:                    sina nf_AU0 —— 人民币/克

换算公式：
    USD/oz ≈ CNY/g × 31.1035 / USDCNH
    CNY/g ≈ USD/oz × USDCNH / 31.1035

沪金相对外盘常有 30~80 美元升水（内地供需 + 汇率预期），
换算值仅供参考，实际以两地实时价为准。
"""

import re
import urllib.request
from typing import Optional, Tuple

# 每盎司 = 31.1035 克
OZ_TO_GRAM = 31.1035

# 默认汇率兜底（用于外网挂掉时的换算 fallback）
DEFAULT_USDCNH = 7.10


def _sina_fetch(code: str) -> Optional[str]:
    """从新浪 hq.sinajs.cn 拉一条实时数据，返回引号内内容"""
    try:
        url = f"https://hq.sinajs.cn/list={code}"
        req = urllib.request.Request(
            url, headers={"Referer": "https://finance.sina.com.cn"}
        )
        raw = urllib.request.urlopen(req, timeout=5).read().decode(
            "gbk", errors="ignore"
        )
        m = re.search(r'"([^"]+)"', raw)
        return m.group(1) if m else None
    except Exception:
        return None


def fetch_comex_gold() -> Optional[float]:
    """
    拉取 COMEX 纽约黄金主力现价 (USD/oz)
    hf_GC 格式: 现价,买价,卖价,最高,最低,开盘,时间,昨收,昨结,...
    """
    payload = _sina_fetch("hf_GC")
    if not payload:
        return None
    try:
        parts = payload.split(",")
        return float(parts[0])
    except (ValueError, IndexError):
        return None


def fetch_shanghai_gold() -> Optional[float]:
    """
    拉取沪金主力现价 (CNY/g)
    nf_AU0 格式: 名称,量,昨结,今开,最高,最低,买价,卖价,现价,昨收,...
    """
    payload = _sina_fetch("nf_AU0")
    if not payload:
        return None
    try:
        parts = payload.split(",")
        # 现价在 index 8，兜底用 index 3（最高/开盘之一）
        for idx in (8, 3, 6, 7):
            try:
                v = float(parts[idx])
                if v > 100:  # 沪金合理区间在几百 CNY/g
                    return v
            except (ValueError, IndexError):
                continue
        return None
    except Exception:
        return None


def fetch_usdcnh() -> Optional[float]:
    """
    拉取美元离岸人民币汇率
    fx_susdcnh 格式: 时间,买价,卖价,现价,...
    """
    payload = _sina_fetch("fx_susdcnh")
    if not payload:
        return None
    try:
        parts = payload.split(",")
        # 现价通常在 index 1 或 8
        for idx in (8, 1, 2):
            try:
                v = float(parts[idx])
                if 5.0 < v < 10.0:  # 汇率合理区间
                    return v
            except (ValueError, IndexError):
                continue
        return None
    except Exception:
        return None


def cny_g_to_usd_oz(cny_per_gram: float, usdcnh: Optional[float] = None) -> float:
    """CNY/g → USD/oz 换算"""
    if usdcnh is None or usdcnh <= 0:
        usdcnh = DEFAULT_USDCNH
    return cny_per_gram * OZ_TO_GRAM / usdcnh


def usd_oz_to_cny_g(usd_per_oz: float, usdcnh: Optional[float] = None) -> float:
    """USD/oz → CNY/g 换算"""
    if usdcnh is None or usdcnh <= 0:
        usdcnh = DEFAULT_USDCNH
    return usd_per_oz * usdcnh / OZ_TO_GRAM


def format_gold(
    usd_per_oz: Optional[float] = None,
    cny_per_gram: Optional[float] = None,
    pct: Optional[float] = None,
    label: str = "黄金",
    show_source: bool = False,
) -> str:
    """
    统一金价显示格式：**美元/盎司为主，人民币/克括号备注**

    参数：
        usd_per_oz: COMEX/伦敦金现价（美元/盎司）
        cny_per_gram: 沪金现价（人民币/克）
        pct: 涨跌幅 %（对应 usd_per_oz 或 cny_per_gram 的涨跌）
        label: 显示前缀（如 "黄金"、"COMEX金"、"沪金"）
        show_source: 是否标注数据源（"外盘"/"沪金"）

    返回示例：
        "黄金 $4077.59/oz (¥905/g) +0.35%"
        "黄金 $4077.59/oz (换算 ¥904/g) +0.35%"（仅美元源时换算）
    """
    # 优先使用直接采集的 USD/oz；如缺则从 CNY/g 换算
    if usd_per_oz is None and cny_per_gram is not None:
        usdcnh = fetch_usdcnh()
        usd_per_oz = cny_g_to_usd_oz(cny_per_gram, usdcnh)
        parts = [f"{label} ${usd_per_oz:.2f}/oz (¥{cny_per_gram:.2f}/g)"]
        if show_source:
            parts[0] += " [沪金推算]"
    elif usd_per_oz is not None and cny_per_gram is None:
        usdcnh = fetch_usdcnh()
        cny_per_gram = usd_oz_to_cny_g(usd_per_oz, usdcnh)
        parts = [f"{label} ${usd_per_oz:.2f}/oz (换算 ¥{cny_per_gram:.2f}/g)"]
        if show_source:
            parts[0] += " [外盘]"
    elif usd_per_oz is not None and cny_per_gram is not None:
        parts = [f"{label} ${usd_per_oz:.2f}/oz (¥{cny_per_gram:.2f}/g)"]
        if show_source:
            parts[0] += " [双源]"
    else:
        return f"{label} 数据缺失"

    if pct is not None:
        parts.append(f"{pct:+.2f}%")

    return " ".join(parts)


def get_gold_snapshot() -> dict:
    """
    一站式获取金价快照，返回统一字段
    
    返回结构：
    {
        "usd_oz": 4077.59,        # COMEX 美元/盎司
        "cny_g": 902.76,          # 沪金 人民币/克
        "usdcnh": 6.8051,          # 美元汇率
        "premium_usd": 48.5,       # 沪金对外盘升水（美元/盎司）
        "formatted": "黄金 $4077.59/oz (¥902.76/g)",
    }
    """
    usd_oz = fetch_comex_gold()
    cny_g = fetch_shanghai_gold()
    usdcnh = fetch_usdcnh() or DEFAULT_USDCNH

    result = {
        "usd_oz": usd_oz,
        "cny_g": cny_g,
        "usdcnh": usdcnh,
    }

    # 计算升水
    if usd_oz and cny_g:
        implied_usd = cny_g_to_usd_oz(cny_g, usdcnh)
        result["premium_usd"] = round(implied_usd - usd_oz, 2)

    # 统一格式化
    result["formatted"] = format_gold(usd_per_oz=usd_oz, cny_per_gram=cny_g)

    return result


if __name__ == "__main__":
    # 自测
    snap = get_gold_snapshot()
    print("=== 金价快照 ===")
    print(f"COMEX 金:  {snap['usd_oz']} USD/oz")
    print(f"沪金主力:  {snap['cny_g']} CNY/g")
    print(f"USDCNH:   {snap['usdcnh']}")
    if "premium_usd" in snap:
        print(f"沪金升水:  {snap['premium_usd']} USD/oz")
    print(f"格式化:    {snap['formatted']}")
    print()
    print("=== 场景示例 ===")
    print("双源:  ", format_gold(usd_per_oz=4077.59, cny_per_gram=902.76, pct=0.35))
    print("仅美元:", format_gold(usd_per_oz=4077.59, pct=-0.5, show_source=True))
    print("仅人民币:", format_gold(cny_per_gram=902.76, pct=1.2, show_source=True))
