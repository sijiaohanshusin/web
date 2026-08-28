# -*- coding: utf-8 -*-
"""把截图的一块放大出来看细节。

补的洞：1440x900 的整页图里，一个焊盘只有几十像素，「是金环还是黑饼」这种
问题在原图上分辨不出来，而它恰恰决定材质调对没调对。

    python scripts/crop.py .shots/forge-078.png --box 840 250 960 370 --zoom 4
    python scripts/crop.py .shots/forge-078.png --grid 3    # 切九宫格逐块看
    python scripts/crop.py .shots/media-center.png --rows 3  # 长页面按高度切片

--box 是 left top right bottom（像素，原图坐标）。输出写到同目录，
文件名加 -crop / -gN / -rN 后缀。放大用 NEAREST，避免插值把噪点抹平骗过眼睛。

输出**任一边都不会超过 MAX_SIDE（2000px）**，超了自动等比缩小并提示。
原因：读图有 2000px 的硬上限，而 `--full-page` 截出来的长页面动辄三四千像素高，
直接读会被拒。长页面要么用 --rows 切片看全貌，要么用 --box 看细节。
"""
import argparse
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent

# 读图工具的硬上限。超过这个尺寸的图会被直接拒收，所以在写出时就兜住。
MAX_SIDE = 2000


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--box", nargs=4, type=int, metavar=("L", "T", "R", "B"))
    ap.add_argument("--zoom", type=float, default=3.0)
    ap.add_argument("--grid", type=int, help="改为切成 N×N 块，每块单独放大")
    ap.add_argument("--rows", type=int, help="改为按高度切成 N 条，看长页面用")
    args = ap.parse_args()

    src = Path(args.image)
    if not src.is_absolute():
        src = REPO / src
    if not src.exists():
        raise SystemExit(f"找不到 {src}")

    im = Image.open(src).convert("RGB")
    print(f"原图 {im.width}x{im.height}")

    def save(region: Image.Image, suffix: str) -> None:
        z = args.zoom
        out = region.resize((int(region.width * z), int(region.height * z)), Image.NEAREST)
        note = ""
        if max(out.width, out.height) > MAX_SIDE:
            # 缩小用 LANCZOS：这一步是为了能看，不是为了看噪点
            shrink = MAX_SIDE / max(out.width, out.height)
            out = out.resize((max(1, int(out.width * shrink)),
                             max(1, int(out.height * shrink))), Image.LANCZOS)
            note = f"（已缩到 {MAX_SIDE}px 上限内，细节请用 --box）"
        dst = src.with_name(f"{src.stem}-{suffix}{src.suffix}")
        out.save(dst)
        print(f"  {dst.relative_to(REPO)}  {out.width}x{out.height} {note}")

    if args.rows:
        n = args.rows
        h = im.height // n
        for r in range(n):
            bottom = im.height if r == n - 1 else (r + 1) * h
            save(im.crop((0, r * h, im.width, bottom)), f"r{r}")
    elif args.grid:
        n = args.grid
        w, h = im.width // n, im.height // n
        for r in range(n):
            for c in range(n):
                save(im.crop((c * w, r * h, (c + 1) * w, (r + 1) * h)), f"g{r}{c}")
    else:
        box = tuple(args.box) if args.box else (0, 0, im.width, im.height)
        save(im.crop(box), "crop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
