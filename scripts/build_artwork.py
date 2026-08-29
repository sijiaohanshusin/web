# -*- coding: utf-8 -*-
"""美术资产加工：母图（PNG）→ 站上用的 webp。

分工和字体那套一样：**母图不入库**（放 `.artsrc/`，几 MB 一张），
入库的是这个脚本产出的 webp。母图的来源与提示词记在
`docs/美术资产清单.md` 与 `docs/AI美术资产生成记录.md` 里，丢了能重新生成。

做三件事：

1. **纹理去接缝。** 只对「要四方连续」的那几张做：把图沿两轴各滚半幅，
   于是原来的边界跑到中间，再在那两条线上做羽化混合。这是确定性的几何操作，
   比让生成器重画一版可靠。（焊点微距那张是浅景深特写，本来就不需要平铺，
   不做这一步 —— 对它做只会把主体糊掉。）
2. **降采样。** 2048² 的纹理在站上是以几百 px 平铺、透明度 0.5 以下叠着用的，
   512² 完全够；不降的话每个访客要为一层几乎看不见的材质下几百 KB。
3. **转 webp。** 暗部渐变对压缩很敏感，所以质量给到 88，并且**用脚本量一遍
   转换前后的暗部直方图**，出现色带就报出来 —— 这类问题在缩略图上看不见。

跑法：
    python scripts/build_artwork.py            # 全部
    python scripts/build_artwork.py --only tex-fr4-weave
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / ".artsrc"
OUT = REPO / "app" / "static" / "img"

# name → (是否要四方连续, 输出边长/宽度, webp 质量)
# 尺寸的依据：纹理按平铺尺寸给，横幅按站上最宽的容器（1240）× 2 给。
JOBS: dict[str, dict] = {
    "tex-fr4-weave":          {"tile": True,  "size": 512,  "q": 88},
    "tex-etched-copper":      {"tile": True,  "size": 512,  "q": 88},
    "tex-matte-solder-mask":  {"tile": True,  "size": 512,  "q": 88},
    # 浅景深特写，不平铺；当局部材质用，给大一点
    "tex-solder-joint":       {"tile": False, "size": 1024, "q": 86},
    "banner-intro":           {"tile": False, "size": 1920, "q": 84},
    "banner-training":        {"tile": False, "size": 1920, "q": 84},
    "banner-hardware":        {"tile": False, "size": 1920, "q": 84},
    "banner-software":        {"tile": False, "size": 1920, "q": 84},
    "banner-contest":         {"tile": False, "size": 1920, "q": 84},
    "banner-social-card":     {"tile": False, "size": 1200, "q": 88},
    "illustration-soldering-journey": {"tile": False, "size": 1280, "q": 86},
}


def make_seamless(im):
    """和「滚半幅的副本」交叉淡化，得到真正可四方连续的图。

    原理，两句话：

    - **滚半幅之后，新的四条外边其实是原图内部相邻的两列/两行**（滚 w/2 时，
      原来 x=w/2 的像素到了 x=0，原来 x=w/2-1 的到了 x=w-1，这两列在原图里紧邻）。
      所以滚过的副本**本身就能无缝平铺**，只是它把不连续搬到了正中间。
    - 于是用一张「中间为 1、四边为 0」的权重图，把原图（中间连续）和滚过的副本
      （四边连续）混起来：`out = im*W + rolled*(1-W)`。四边取自副本 → 平铺无缝；
      中间取自原图 → 副本那道中缝被盖掉。

    第一版写成了「在中缝上做镜像混合」，那是另一回事 —— 镜像会造出一条对称轴，
    接缝反而更明显（实测接缝差从 2.72 涨到 5.25）。判据一直在，是我读错了方向。
    """
    import numpy as np

    a = np.asarray(im, dtype=np.float32)
    h, w = a.shape[:2]
    rolled = np.roll(np.roll(a, w // 2, axis=1), h // 2, axis=0)

    def ramp(n: int) -> "np.ndarray":
        # 距最近边缘的归一化距离，在 1/4 幅处达到 1；再用 smoothstep 去掉折角
        d = np.minimum(np.arange(n), n - 1 - np.arange(n)) / (n / 4.0)
        d = np.clip(d, 0.0, 1.0)
        return d * d * (3 - 2 * d)

    wgt = np.outer(ramp(h), ramp(w))[:, :, None]
    out = a * wgt + rolled * (1 - wgt)
    from PIL import Image

    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype("uint8"), im.mode)


def dark_histogram_gaps(im) -> int:
    hist = im.convert("L").histogram()[:64]
    used = [i for i, n in enumerate(hist) if n > 0]
    if not used:
        return 0
    return sum(1 for i in range(used[0], used[-1] + 1) if hist[i] == 0)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="美术资产加工")
    ap.add_argument("--only", help="只处理这一个（不带扩展名）")
    args = ap.parse_args()

    try:
        from PIL import Image
    except ImportError:
        print("需要 Pillow：python -m pip install pillow（开发工具，不进 requirements）")
        return 2

    if not SRC.exists():
        print(f"找不到母图目录 {SRC.relative_to(REPO)}/ —— 把生成的 PNG 放进去。")
        print("（母图不入库，几 MB 一张；入库的是这个脚本产出的 webp）")
        return 1

    total_in = total_out = 0
    for name, job in JOBS.items():
        if args.only and name != args.only:
            continue
        src = SRC / f"{name}.png"
        if not src.exists():
            print(f"  --   {name}.png 不在 .artsrc/，跳过")
            continue
        im = Image.open(src).convert("RGB")
        before = dark_histogram_gaps(im)
        # **先降采样，再去接缝。** 反过来做等于白做：Lanczos 在图像边界不做环绕，
        # 它按「边缘外的像素等于边缘像素」来算，于是刚刚对齐好的两条边又被各自
        # 改写一遍，接缝重新出现（实测比值 5.01，和没处理差不多）。
        w, h = im.size
        target = job["size"]
        if w >= h:
            im = im.resize((target, round(h * target / w)), Image.LANCZOS)
        else:
            im = im.resize((round(w * target / h), target), Image.LANCZOS)
        if job["tile"]:
            im = make_seamless(im)
        dst = OUT / f"{name}.webp"
        im.save(dst, "WEBP", quality=job["q"], method=6)
        after = dark_histogram_gaps(Image.open(dst))
        in_kb = src.stat().st_size / 1024
        out_kb = dst.stat().st_size / 1024
        total_in += in_kb
        total_out += out_kb
        flag = ""
        if after > before + 3:
            flag = f"  ← 暗部色带变多（{before}→{after}），质量要调高"
        print(f"  {name:34} {im.size[0]:>4}x{im.size[1]:<4} "
              f"{in_kb:7.0f} KB → {out_kb:6.0f} KB{flag}")
    print(f"\n合计 {total_in / 1024:.1f} MB → {total_out:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
