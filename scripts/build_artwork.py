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

# name → (是否要四方连续, 输出边长/宽度, webp 质量, 可选 sat=饱和度倍数, src=母图名)
#
# **`sat` 是为「大面积平铺」加的，不是为了好看。** 全站配色是近黑 + 信号青 + 焊锡铜
# 三支，而 FR4 的母图是一张饱和的绿色阻焊照片：铺在页脚那 400px 里读起来是「板子的
# 背面」（真实、也没人会当成设计色），但铺满一个 900px 高的分镜之后，整块就变成
# **绿色色块** —— 实测把区块从 (5,5,6) 抬到 (7.6, 14.0, 11.8)，绿比红高 6.4。
# 那是往配色里塞了第四支颜色。
#
# 压饱和度而不是压透明度：纹理靠的是**亮度起伏**，去掉颜色之后 p95−p5 跨度
# 从 17 只掉到 16（几乎不掉），而绿比红从 +8 降到 +3。也就是「材质留下，颜色收走」。

# 尺寸的依据：纹理按平铺尺寸给，横幅按站上最宽的容器（1240）× 2 给。
#
# **`tex-matte-solder-mask` 已从这里移除**（母图还在 `.artsrc/`）：它压出来只有 2KB，
# p95−p5 跨度 2 —— 也就是几乎没有纹理，而且站上没有它的去处。理由写在
# `docs/美术资产清单.md`。不做而不是留着，是因为留着会让新加的「纹理必须真的有
# 纹理」那条断言常红，而常红的断言等于没有断言。
JOBS: dict[str, dict] = {
    "tex-fr4-weave":          {"tile": True,  "size": 512,  "q": 88, "sat": 0.4},
    # 母图是裸铜棚拍，平均亮度 32 —— 铺满一个分镜会把整块抬成中灰。
    # `tone` 把它压到「平均 12、跨度 15」：近黑底上一层能看见的铜面，见 retone()。
    "tex-etched-copper":      {"tile": True,  "size": 512,  "q": 88, "sat": 0.55,
                               "tone": (12, 15)},
    # 白区材质。质量给到 92：浅色低对比的图最经不起有损压缩 ——
    # 88 就会把那层极淡的纹理压成块，而它整张的明暗跨度只有 23 级。
    #
    # `tone` 提亮到「平均 245、跨度 12」。**白区的材质强度直接就是文字对比度预算**：
    # 暗材质有大把抬升余量（底色 5，往上很远都还是黑），而浅材质只能往下压 ——
    # 纸白已经是 248，再亮就顶到 255。母图平均 236.5、最暗 5% 约 223，铺上去把
    # 白区压到中位 225，于是 eyebrow 那 13px 小字跌破 4.5:1，而全套浏览器脚本
    # 一条都不会红（理由见 check_artwork.py 里那条断言）。
    # 241/15 是把「纹理够看得见」和「文字够对比」一起满足的那一档：实测最暗 5%
    # 落在 234，配上压暗一档的 `--accent-ink` 还有 4.68:1。**留了余量是刻意的** ——
    # webp 有损压缩会再吃掉 1~2 级跨度（(245,12) 那档压完只剩 11.3，反而跌破 12）。
    "tex-copper-light":       {"tile": True,  "size": 512,  "q": 92,
                               "tone": (241, 15)},
    # 浅景深特写，不平铺；当局部材质用，给大一点
    "tex-solder-joint":       {"tile": False, "size": 1024, "q": 86},
    "banner-intro":           {"tile": False, "size": 1920, "q": 84},
    "banner-training":        {"tile": False, "size": 1920, "q": 84},
    "banner-hardware":        {"tile": False, "size": 1920, "q": 84},
    "banner-software":        {"tile": False, "size": 1920, "q": 84},
    "banner-contest":         {"tile": False, "size": 1920, "q": 84},
    "banner-social-card":     {"tile": False, "size": 1200, "q": 88},
    # 列表页页头氛围（`.nf-scope` 的 --scope-art）。母图 2560x860，输出 1920：
    # 页头最宽就是视口宽，而这几张是柔光氛围、没有需要 1:1 像素的细节。
    # 质量给到 86 而不是横幅的 84 —— hero-news 那张有一排细竖条，84 会让它起毛边。
    "hero-news":              {"tile": False, "size": 1920, "q": 86},
    "hero-events":            {"tile": False, "size": 1920, "q": 86},
    "hero-resources":         {"tile": False, "size": 1920, "q": 86},
    "hero-works":             {"tile": False, "size": 1920, "q": 86},
    "hero-honors":            {"tile": False, "size": 1920, "q": 86},
    "hero-team":              {"tile": False, "size": 1920, "q": 86},
    "hero-leaderboard":       {"tile": False, "size": 1920, "q": 86},
    # 新生指南开篇三联画。第 1 张就是第一批那张，只是改个名进套 ——
    # 母图不用重新生成，所以这里用 src 指过去。
    "illu-journey-1":         {"tile": False, "size": 1280, "q": 86,
                               "src": "illustration-soldering-journey"},
    "illu-journey-2":         {"tile": False, "size": 1280, "q": 86},
    "illu-journey-3":         {"tile": False, "size": 1280, "q": 86},
    # 首屏大氛围图（`.nf-hero::before` 的 --hero-art）。母图 2400x1800（4:3），
    # 输出 1920 长边：第一屏最宽就是视口宽，柔光氛围没有要 1:1 的细节。
    # 质量 88 比页头那批高一档 —— 这张有一片从近到远的连续渐变，86 会在纵深方向
    # 起色带（页头那批是平的柔光，吃不到这个问题）。它照样只有几十 KB。
    "hero-home":              {"tile": False, "size": 1920, "q": 88},
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


def retone(im, target_mean: float, target_spread: float):
    """把一张图重映射到「指定的平均亮度 + 指定的明暗跨度」。

    **为什么需要它**：`tex-etched-copper` 的母图是一张裸铜棚拍，平均亮度 32、
    跨度 20 —— 直接铺满一个分镜，整块就从 #050506 抬到中灰，那不是「近黑底上有
    材质」而是「页面变灰了」。而单纯压暗（整体乘一个系数）会把跨度一起压掉：
    乘 0.33 之后平均是 11、跨度只剩 6.6，低于「上面真的有纹理」那条线（12）。

    所以要把**平均**和**跨度**分开控制：先按跨度算缩放系数，再把中心平移到目标
    平均值。`out = (in − 原均值) × k + 目标均值`，三个通道用同一组数 ——
    这样通道之间的差值（也就是铜色的暖调）按 k 等比收窄，不会变色。

    FR4 那张不用 retone：它的母图本来就是暗的（平均 7.6），分布也是「大部分极暗
    + 织纹高光」，正好是暗材质该有的样子。

    最后那一步**抖动（dither）是必需的**：`ImageEnhance.Color` 已经量化过一次到
    8bit，再乘一个非整数系数取整，会有个别输出灰阶一次都取不到 —— 于是暗部直方图
    出现梳齿，`check_artwork.py` 的「暗部无色带」当场判红（实测 3 个空档）。
    在取整前加 ±0.5 的噪声就能把空档填上，而这一层噪声的幅度小于一个灰阶、
    肉眼看不到。种子写死，保证同样的母图每次出一样的产物。
    """
    import numpy as np

    a = np.asarray(im, dtype=np.float32)
    lum = a.mean(axis=2)
    m = float(lum.mean())
    spread = float(np.percentile(lum, 95) - np.percentile(lum, 5))
    k = target_spread / max(spread, 0.001)
    out = (a - m) * k + target_mean
    rng = np.random.default_rng(20260829)
    out = out + rng.uniform(-0.5, 0.5, out.shape)
    from PIL import Image

    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype("uint8"), "RGB")


def dark_histogram_gaps(im) -> int:
    """和 `check_artwork.py` 的 `banding_score` 同一套判据，保持一致。

    只在「像素够多」的灰阶之间数空档 —— 高光尾巴上一两个像素造成的 0
    不是色带（理由写在那个函数里）。
    """
    g = im.convert("L")
    hist = g.histogram()[:64]
    floor = max(4, (g.size[0] * g.size[1]) // 20000)
    dense = [i for i, n in enumerate(hist) if n >= floor]
    if len(dense) < 2:
        return 0
    return sum(1 for i in range(dense[0], dense[-1] + 1) if hist[i] == 0)


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
        src = SRC / f"{job.get('src', name)}.png"
        if not src.exists():
            print(f"  --   {src.name} 不在 .artsrc/，跳过")
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
        # 压饱和度放在最后：去接缝是在像素上做混合，先压不影响结果，
        # 但放最后能保证「量到的就是入库的那张」。
        if job.get("sat") is not None:
            from PIL import ImageEnhance
            im = ImageEnhance.Color(im).enhance(job["sat"])
        if job.get("tone") is not None:
            im = retone(im, *job["tone"])
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
