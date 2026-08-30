# -*- coding: utf-8 -*-
"""把获奖证书的照片处理成入库的 webp。

    python scripts/build_certs.py            # 全部
    python scripts/build_certs.py --list     # 只看清单与源文件在不在

**为什么产物要提交进仓库**：`Honor.certificate` 是 `ImageField`，落在 `MEDIA_ROOT`
下，而 `app/media/` 是 gitignore 的 —— 也就是说本地导入的图**到不了生产**。所以
处理后的 webp 放在 `app/news/data/honors/`（跟着代码走），由
`manage.py import_honors` 在生产上把它们喂给 `ImageField`。这是一次性数据导入，
不是运行时依赖。

源文件是招新 PPT 里内嵌的照片（`.artsrc/certs/`，母图不入库，和美术资产同一个
约定）。抽取方式见 docs/荣誉数据来源.md。

尺寸：长边压到 1400。证书是拍下来的纸，要能读清奖项名与队员姓名，但不需要原始
分辨率 —— 1400 长边下正文字号约 20px，够读，而体积只有原图的几分之一。
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / ".artsrc" / "certs"
OUT = REPO / "app" / "news" / "data" / "honors"

LONG_EDGE = 1400
QUALITY = 86

# (输出名, 源文件名)。源文件名是 PPT 里的内嵌图编号，保留它是为了能回溯。
#
# **刻意没收进来的两张**：image106（第十八届智能车 独轮车组 国一）与 image109
# （TRIZ 杯创新方法大赛 国一）在 PPT 里只有 309x433 —— 那个尺寸放到证书墙上是
# 一块糊斑。这两项的奖项信息照样录（PPT 正文里有），只是没有证书照。
CERTS = [
    ("esdc-2026-chip-first",      "esdc-2026-chip-first.jpg"),
    ("esdc-2025-chip-second",     "image89.jpeg"),
    ("datang-2025-ict-first",     "image91.jpeg"),
    ("smartcar-2025-hover-first", "image90.png"),
    ("nuedc-2024-ti-second",      "image77.jpeg"),
    ("copyright-2024-rsta",       "image85.png"),
    ("icm-2024-meritorious",      "image79.jpeg"),
    ("nuedc-2023-second-b2356",   "image78.jpg"),
    ("nuedc-2023-second-b2363",   "image102.jpeg"),
    ("esdc-2023-fpga-second",     "image86.jpg"),
    ("nuedc-2021-first-b1058",    "image51.jpeg"),
    ("nuedc-2021-first-b1059",    "image74.png"),
    ("smartcar-2021-emag-first",  "image73.png"),
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="证书照片 → webp")
    ap.add_argument("--list", action="store_true", help="只列清单，不处理")
    args = ap.parse_args()

    try:
        from PIL import Image
    except ImportError:
        print("需要 Pillow：python -m pip install pillow（开发工具，不进 requirements）")
        return 2

    missing = [src for _, src in CERTS if not (SRC / src).exists()]
    if args.list or missing:
        print(f"源目录 {SRC}")
        for name, src in CERTS:
            path = SRC / src
            mark = "OK " if path.exists() else "缺 "
            size = f"{path.stat().st_size / 1024:.0f} KB" if path.exists() else "—"
            print(f"  {mark} {name:28s} ← {src:24s} {size}")
        if missing:
            print(f"\n缺 {len(missing)} 个源文件，先把它们放进 {SRC}")
            return 1
        if args.list:
            return 0

    OUT.mkdir(parents=True, exist_ok=True)
    total_in = total_out = 0
    for name, src in CERTS:
        im = Image.open(SRC / src)
        im = im.convert("RGB")
        w, h = im.size
        scale = min(1.0, LONG_EDGE / max(w, h))
        if scale < 1.0:
            im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        dest = OUT / f"{name}.webp"
        im.save(dest, "WEBP", quality=QUALITY, method=6)
        size_in = (SRC / src).stat().st_size
        size_out = dest.stat().st_size
        total_in += size_in
        total_out += size_out
        print(f"  {name:28s} {w}x{h} → {im.size[0]}x{im.size[1]}  "
              f"{size_in / 1024:6.0f} KB → {size_out / 1024:5.0f} KB")

    print(f"\n合计 {total_in / 1024 / 1024:.1f} MB → {total_out / 1024:.0f} KB  "
          f"（{len(CERTS)} 张，写到 {OUT.relative_to(REPO)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
