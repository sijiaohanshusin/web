# -*- coding: utf-8 -*-
"""把协会现场照裁成素材槽要的比例，输出 webp。

    python scripts/build_photos.py

**为什么要预裁，而槽位明明是 `object-fit: cover`**：cover 默认从中心裁，而这几张
照片「哪一部分不能丢」各不一样 —— 合影不能切到人头，颁奖照不能切掉横幅上的赛事
名，工作台照不能把示波器和板子只留一头。所以在这里按每张的情况定锚点，
到了页面上 cover 就只是「刚好铺满」而不会再动构图。

**为什么走 `SlotSpec.fallback` 而不是让站务在 `/dashboard/media/` 上传**：
`MediaSlot.image` 落在 `MEDIA_ROOT`（`app/media/` 被 gitignore），本地传的图到不了
生产。`fallback` 指向 `static` 下的文件，跟着代码走 —— 而它的语义正是「协会自有的、
已提交进仓库的照片」。

母图在 `.artsrc/photos/`（不入库，同美术资产的约定），来源见 docs/荣誉数据来源.md。
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / ".artsrc" / "photos"
OUT = REPO / "app" / "static" / "img" / "photo"

# (输出名, 源文件, 目标比例, 竖向锚点, 说明)
#
# 竖向锚点 0=顶 .5=中 1=底，只在需要裁掉高度时用得上（源比目标"高"的时候）。
PHOTOS = [
    ("group-2024", "image1.jpeg", 12 / 5, .583,
     "全员合影：约 60 人排成一条横带（源图里人从 x=82 铺到 1862，两端几乎没有"
     "余量），所以只能裁上下、不能裁两侧。锚点 .583 把 1288 高里多出来的 484px "
     "按 282 上 / 202 下分掉 —— 天花板与地砖各留约 130px，人和背景板占满其余部分。"
     "槽位比例同步改成 12/5，走廊是等高胶片条，见 home.css 的 .nf-tile"),
    ("award-ti-2024", "image41.jpeg", 4 / 3, .5,
     "颁奖台合影：横幅上「2024 年 TI 杯…二等奖」要留住，所以只从两侧裁"),
    ("lab-debug", "image42.jpeg", 4 / 3, .5,
     "赛场调试：老师 + 三名队员围着示波器。人都在中间"),
    ("bench-scopes", "image26.jpg", 16 / 9, .42,
     "工作台：两台示波器在上、开发板在下。锚点略偏上 —— "
     "居中裁会把下排板子切掉一半，而「有在用的痕迹」全在那排板子上"),
]

# q78 是逐张对比过的：和 q84 在 3 倍放大下看不出差别（这几张都是室内实拍，
# 细节本来就被噪点和景深糊掉了），但六张走廊图合起来省下约 90KB。
# 换成插画或者带大片平涂的图要重新验 —— 那类图在低 q 上先出色带。
QUALITY = 78
MAX_W = 1600


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        from PIL import Image
    except ImportError:
        print("需要 Pillow：python -m pip install pillow（开发工具，不进 requirements）")
        return 2

    missing = [s for _, s, _, _, _ in PHOTOS if not (SRC / s).exists()]
    if missing:
        print(f"源目录 {SRC}")
        for name, src, _, _, _ in PHOTOS:
            print(f"  {'OK ' if (SRC / src).exists() else '缺 '} {name:16s} ← {src}")
        print(f"\n缺 {len(missing)} 个源文件")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    for name, src, ratio, anchor, why in PHOTOS:
        im = Image.open(SRC / src).convert("RGB")
        w, h = im.size
        cur = w / h
        if cur > ratio:                      # 源更宽 → 裁两侧（居中）
            new_w = round(h * ratio)
            left = (w - new_w) // 2
            im = im.crop((left, 0, left + new_w, h))
        elif cur < ratio:                    # 源更高 → 裁上下（按锚点）
            new_h = round(w / ratio)
            top = round((h - new_h) * anchor)
            im = im.crop((0, top, w, top + new_h))
        if im.width > MAX_W:
            im = im.resize((MAX_W, round(MAX_W / ratio)), Image.LANCZOS)

        dest = OUT / f"{name}.webp"
        im.save(dest, "WEBP", quality=QUALITY, method=6)
        print(f"  {name:16s} {w}x{h} ({cur:.2f}) → {im.size[0]}x{im.size[1]} "
              f"({im.width / im.height:.2f})  {dest.stat().st_size / 1024:5.0f} KB")
        print(f"                   {why}")
    print(f"\n写到 {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
