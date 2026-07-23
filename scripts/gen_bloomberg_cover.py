#!/usr/bin/env python3
"""自动生成 Bloomberg 日报封面图（用系统 python3 + PIL）"""
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import os

w, h = 900, 506
img = Image.new("RGB", (w, h), color=(15, 76, 129))  # Bloomberg Blue #0F4C81
draw = ImageDraw.Draw(img)

font_paths = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
]
font_title = font_sub = font_date = None
for fp in font_paths:
    if os.path.exists(fp):
        try:
            font_title = ImageFont.truetype(fp, 38)
            font_sub = ImageFont.truetype(fp, 22)
            font_date = ImageFont.truetype(fp, 18)
            break
        except Exception:
            continue
if font_title is None:
    font_title = font_sub = font_date = ImageFont.load_default()

# 主标题
title = "彭博社发文日报"
tb = draw.textbbox((0, 0), title, font=font_title)
draw.text(((w - (tb[2] - tb[0])) / 2, 140), title, fill="white", font=font_title)

# 英文副标题
sub = "Bloomberg Daily Digest"
sb = draw.textbbox((0, 0), sub, font=font_sub)
draw.text(((w - (sb[2] - sb[0])) / 2, 200), sub, fill=(180, 200, 220), font=font_sub)

# 装饰线
draw.line([(100, 280), (800, 280)], fill=(100, 150, 180), width=2)

# 日期
today = datetime.now().strftime("%Y-%m-%d")
db = draw.textbbox((0, 0), today, font=font_date)
draw.text(((w - (db[2] - db[0])) / 2, 300), today, fill=(200, 215, 230), font=font_date)

# 底部标签
tag = "AI边用边想 · 每日精选"
tgb = draw.textbbox((0, 0), tag, font=font_date)
draw.text(((w - (tgb[2] - tgb[0])) / 2, 400), tag, fill=(150, 170, 190), font=font_date)

os.makedirs("post-to-wechat", exist_ok=True)
out = "post-to-wechat/bloomberg-cover.png"
img.save(out, "PNG")
print(f"[publish] 封面图已生成: {out}")
