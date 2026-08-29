# -*- coding: utf-8 -*-
"""美术资产验收：按 `docs/美术资产清单.md` 里那五条硬标准逐张量。

**为什么要脚本量而不是只看图**：这五件事里有三件肉眼在缩略图上看不出来 ——
色带要拉直方图才知道、接缝要拼 2x2 才现形、横幅左侧留白够不够要按区域算亮度。
而它们全都是「接进站里之后才显形」的那类问题。

跑法：
    python scripts/check_artwork.py                 # 量全部
    python scripts/check_artwork.py --dump .shots/aw   # 另存拼接图与直方图，人眼复核
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
IMG = REPO / "app" / "static" / "img"

# 量的是**站上实际引用的 webp**，不是 `.artsrc/` 里的母图：母图不入库（几 MB
# 一张），别人 clone 下来没有它，而真正会被访客看到的是这些 webp。
# 母图那一侧的规格（2048²、无 JPEG 块）在 `docs/AI美术资产生成记录.md` 里有记录。
#
# 可四方连续的底纹（大面积平铺用）。
# **`tex-solder-joint` 不在这里** —— 它是浅景深的单个焊点特写，清单里从没要求它
# 平铺，它的用法是「局部材质」。第一版把它一起量了，于是报出一个 7.19 的假红。
# （`tex-matte-solder-mask` 已弃用并删除产物：p95−p5 跨度只有 2，等于没有纹理，
#   而且站上没有它的去处。母图还在 `.artsrc/`，理由见 docs/美术资产清单.md。）
TEXTURES = ["tex-fr4-weave.webp", "tex-etched-copper.webp"]
# 局部材质：只要求暗部无色带与色相正确
SPOT = ["tex-solder-joint.webp"]
# 横幅：左侧要留出压标题的干净区。**这条断言是横幅上白字的唯一保障** ——
# `check_a11y.py` 会跳过图背景的元素（算不出唯一底色），所以那边量不到它。
BANNERS = ["banner-intro.webp", "banner-training.webp", "banner-hardware.webp",
           "banner-software.webp", "banner-contest.webp"]
OTHERS = SPOT + ["banner-social-card.webp"]

# ---------- 第二批（工单在 docs/美术资产清单.md 的「第二批」一节） ----------
# 这一批还没交付，所以**缺文件不算失败**，只打印「待交付」。理由：验收标准写在
# 代码里比写在文档里有用得多（数字不会漂），但不能因此把主线检查卡红 ——
# 那会让人为了让脚本变绿而去删断言。
#
# 列表页页头氛围图：走 `.nf-scope` 的 `--scope-art` 变量（见 core.css）。
# 尺寸与安全区是**算出来的**，不是拍脑袋：页头在桌面是 1440x274（5.26:1）、
# 窄屏是 390x229（1.70:1），`cover` + `right center` 之下
#   桌面看到竖向 22%~78%（整宽）、窄屏看到横向 43%~100%（整高）
# 所以意象必须落在「右 40% × 竖中 56%」这块交集里，左 55% 留给标题与导语。
# 2560x860（≈2.98:1）是让两边裁掉的量大致相等的那个比例。
HERO_ART = {
    "hero-news.webp": "公告与动态",
    "hero-events.webp": "活动",
    "hero-resources.webp": "学习资源",
    "hero-works.webp": "作品墙",
    "hero-honors.webp": "荣誉墙",
    "hero-team.webp": "团队",
    "hero-leaderboard.webp": "积分榜",
}
# 浅底板面材质：白区（#nf-honors 的 .surf-hatch）现在是全站最平的地方，
# 而第一批的覆铜纹是暗材质、铺白区上是一块脏斑。
LIGHT_TEX = ["tex-copper-light.webp"]
# 插画成套（新生指南开篇）。**成套是硬要求**：一张风格孤立的插画会显得像贴上去的，
# 所以验收里有一条「三张的尺寸与色相要一致」。
# 第 1 张就是第一批那张 `illustration-soldering-journey`（改名而来，母图不用重生成），
# 只需要再补 2 张对得上它的。
ILLU = ["illu-journey-1.webp", "illu-journey-2.webp", "illu-journey-3.webp"]

failures: list[str] = []
notes: list[str] = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def note(label, detail=""):
    print(f"  --   {label}" + (f"  {detail}" if detail else ""))
    notes.append(label)


def hue_split(im) -> tuple[float, float, float]:
    """返回 (青系占比, 铜系占比, 紫红占比)，只统计有饱和度的像素。

    判据用 HSV 的色相：青 150~210°，铜/琥珀 20~60°，紫红 270~330°。
    紫红是清单里明确禁止的一支（会和全站配色打架）。
    """
    hsv = im.convert("RGB").resize((256, 256)).convert("HSV")
    px = list(hsv.getdata())
    cyan = copper = magenta = colored = 0
    for h, s, v in px:
        if s < 40 or v < 18:      # 灰与死黑不参与色相统计
            continue
        colored += 1
        deg = h * 360 / 255
        if 150 <= deg <= 210:
            cyan += 1
        elif 20 <= deg <= 60:
            copper += 1
        elif 270 <= deg <= 330:
            magenta += 1
    if not colored:
        return 0.0, 0.0, 0.0
    return cyan / colored, copper / colored, magenta / colored


def texture_spread(im) -> float:
    """材质到底有没有纹理：亮度的 p95 − p5。

    **这条断言是被两次「交了但等于没有」逼出来的。** `tex-matte-solder-mask` 压出来
    只有 2KB、`tex-copper-light` 第一版拉到 24 倍对比度还是一片均匀噪点 —— 两张都
    通过了当时全部的断言（不平铺？平铺。有色带？没有。色相跑了？没跑），
    因为**没有一条在问「这上面有东西吗」**。

    阈值 12 是从实测分出来的，不是猜的（量的都是入库的 webp）：
        tex-fr4-weave     17    有纹理，站上效果成立
        tex-etched-copper 20    有纹理
        tex-solder-joint  73    浅景深照片
        ---- 线 12 ----
        tex-copper-light   3    第一版，均匀噪点
        tex-matte-solder-mask 2 已弃用

    用 p95−p5 而不是 max−min：一两个孤立的亮点/暗点不算纹理，
    而极值对它们极其敏感（那张纯平的图 max−min 是 16，跨度却只有 3）。
    """
    import numpy as np

    a = np.asarray(im.convert("L"), dtype=np.float32)
    return float(np.percentile(a, 95) - np.percentile(a, 5))


def banding_score(im) -> int:
    """暗部色带的粗略指标：0~64 灰阶里「空档」的个数。

    暗调图如果做过量化/JPEG 压缩，暗部直方图会梳齿状 —— 有值的灰阶之间夹着 0。
    连续渐变的图在这一段应该几乎每一级都有像素。
    """
    g = im.convert("L")
    hist = g.histogram()[:64]
    used = [i for i, n in enumerate(hist) if n > 0]
    if not used:
        return 0
    return sum(1 for i in range(used[0], used[-1] + 1) if hist[i] == 0)


def seam_delta(im) -> tuple[float, float]:
    """四方连续检查：返回 (接缝绝对差, 接缝差 / 全图相邻差的中位数)。

    判据是「把首尾两列接在一起，看起来和图内部任意相邻两列一样自然吗」。
    两个数一起返回，因为单看哪一个都会判错：

    - **只看比值**：近乎纯黑的图内部相邻差接近 0，除出来能到 60 以上，而肉眼
      完全看不见接缝（`tex-matte-solder-mask` 就是这样，压成 2KB 说明几乎没细节）。
    - **只看绝对差**：细节丰富的纹理本身相邻列就差好几个灰阶，绝对差不可能小。

    基线必须是**全图相邻差的中位数**，不能拿某一处的相邻差当基准 —— 第一版取
    x = w/3 那一列，而这批纹理带着大尺度明暗梯度，各处的相邻差相差好几倍，
    于是同一张图换个取样点结论就反过来（实测 fr4 布纹：w/3 处 1.15，中间 4.08）。
    这正是「基线取一个样本」的典型翻车。
    """
    import numpy as np

    a = np.asarray(im.convert("L"), dtype=np.float32)
    h, w = a.shape
    wrap = float(np.mean([np.abs(a[:, 0] - a[:, -1]).mean(),
                          np.abs(a[0, :] - a[-1, :]).mean()]))
    col_adj = np.abs(np.diff(a, axis=1)).mean(axis=0)   # 每一对相邻列的平均差
    row_adj = np.abs(np.diff(a, axis=0)).mean(axis=1)
    base = float(np.median(np.concatenate([col_adj, row_adj])))
    return wrap, wrap / max(base, 0.001)


def left_clean(im, frac=0.4) -> tuple[float, float]:
    """横幅左侧留白检查：返回 (左侧 frac 区平均亮度, 右侧平均亮度)。

    标题要压在左边，左侧越暗越干净。只看平均值不够 —— 一小块高光也会毁掉标题，
    所以另外把左区的 99 分位亮度也报出来。
    """
    from statistics import mean

    g = im.convert("L").resize((320, 135))
    px = list(g.getdata())
    w, h = g.size
    cut = int(w * frac)
    left = [px[y * w + x] for y in range(h) for x in range(cut)]
    right = [px[y * w + x] for y in range(h) for x in range(cut, w)]
    left.sort()
    return mean(left), mean(right), left[int(len(left) * .99)]


def region(im, x0f, x1f, y0f=0.0, y1f=1.0):
    """返回一块矩形区域的 (平均亮度, 99 分位, 99.9 分位)。比例参数是 0~1。"""
    import numpy as np

    a = np.asarray(im.convert("L"), dtype=np.float32)
    h, w = a.shape
    box = a[int(h * y0f):int(h * y1f), int(w * x0f):int(w * x1f)]
    return (float(box.mean()), float(np.percentile(box, 99)),
            float(np.percentile(box, 99.9)))


def pending(name, label):
    print(f"  ..   {name} 待交付（{label}）")


def check_batch2(Image) -> None:
    print("\n第二批 · 列表页页头氛围（意象在右 40% × 竖中 56%，左 55% 留给标题）")
    for name, label in HERO_ART.items():
        path = IMG / name
        if not path.exists():
            pending(name, label)
            continue
        im = Image.open(path)
        lmean, l99, _ = region(im, 0.0, 0.55)
        rmean, r99, _ = region(im, 0.60, 1.0)
        _, _, g999 = region(im, 0.0, 1.0)
        cyan, copper, magenta = hue_split(im)
        print(f"\n  {name}  {im.size[0]}x{im.size[1]}  {label}")
        check(2.90 <= im.size[0] / im.size[1] <= 3.06,
              "比例 ≈2.98:1（两边裁掉的量大致相等）", f"{im.size}")
        # 左区收得比第一批（≤80）狠：页头上压着 h1 + 一句 720px 宽的宋体导语，
        # 覆盖面积比章节头大得多，一小块高光就会顶在笔画上。
        check(l99 <= 30, "左 55% 干净（99 分位 ≤30）", f"{l99:.0f}")
        check(lmean < rmean, "左侧比右侧暗", f"左 {lmean:.1f} vs 右 {rmean:.1f}")
        # 窄屏时文字会压到右区上（`cover` 从左边裁），所以右区也不能整片发亮 ——
        # 但允许细高光（第一批实测右区 99 分位到 134，肉眼没问题）。
        check(rmean <= 25, "右 40% 整体仍是暗场（平均 ≤25）", f"{rmean:.1f}")
        check(r99 <= 140, "右 40% 没有大片过曝（99 分位 ≤140）", f"{r99:.0f}")
        check(g999 <= 210, "全图 99.9 分位 ≤210（细高光可以，大面积不行）", f"{g999:.0f}")
        check(magenta < 0.08, "没有紫红色相", f"紫红 {magenta:.1%}")
        note("色相分布", f"青 {cyan:.0%} · 铜 {copper:.0%}")

    print("\n第二批 · 浅底板面材质（白区用，判据和暗材质正好相反）")
    for name in LIGHT_TEX:
        path = IMG / name
        if not path.exists():
            pending(name, "白区底纹")
            continue
        im = Image.open(path)
        seam_abs, seam_ratio = seam_delta(im)
        mean_l, _, _ = region(im, 0.0, 1.0)
        import numpy as np
        lo = float(np.asarray(im.convert("L")).min())
        cyan, copper, magenta = hue_split(im)
        print(f"\n  {name}  {im.size[0]}x{im.size[1]}")
        check(im.size[0] == im.size[1], "是正方形（平铺用）", f"{im.size}")
        check(seam_abs < 1.5 or seam_ratio < 2.0, "接缝不明显", 
              f"绝对 {seam_abs:.2f} · 比值 {seam_ratio:.2f}")
        # 白区底色是 #f7f8fa（亮度 248）。材质要压在它上面当「浅浮雕」，
        # 平均亮度低于 235 就会读成一块脏斑 —— 这是第一批那张暗铜纹放不进白区的原因。
        check(mean_l >= 235, "整体够亮（平均 ≥235，白区底色是 248）", f"{mean_l:.1f}")
        check(lo >= 185, "最暗处也不深（≥185，不能有大块阴影）", f"{lo:.0f}")
        # 第一版就死在这里：又亮又干净，但一片均匀噪点。见 texture_spread 的说明。
        spread = texture_spread(im)
        check(spread >= 12, "**上面真的有纹理**（p95−p5 跨度 ≥12）", f"{spread:.1f}")
        check(magenta < 0.08, "没有紫红色相", f"紫红 {magenta:.1%}")
        note("色相分布", f"青 {cyan:.0%} · 铜 {copper:.0%}")

    print("\n第二批 · 新生指南开篇插画（三张必须像同一支笔画的）")
    got = [(n, Image.open(IMG / n)) for n in ILLU if (IMG / n).exists()]
    for n in ILLU:
        if not (IMG / n).exists():
            pending(n, "开篇插画")
    for name, im in got:
        band = banding_score(im)
        cyan, copper, magenta = hue_split(im)
        print(f"\n  {name}  {im.size[0]}x{im.size[1]}")
        check(band <= 3, "暗部无色带", f"{band} 个空档")
        check(magenta < 0.08, "没有紫红色相", f"紫红 {magenta:.1%}")
        note("色相分布", f"青 {cyan:.0%} · 铜 {copper:.0%}")
    if len(got) == len(ILLU):
        sizes = {im.size for _, im in got}
        check(len(sizes) == 1, "三张尺寸一致（一行并排，不齐就参差）", f"{sizes}")
        # 「成套」不是一句形容词，是可以量的：三张的青/铜配比要在同一个区间里。
        cyans = [hue_split(im)[0] for _, im in got]
        check(max(cyans) - min(cyans) <= 0.35,
              "三张的色相配比接近（否则不像同一支笔）",
              " · ".join(f"{c:.0%}" for c in cyans))
    elif got:
        check(False, "插画必须成套交付（宁缺勿滥）", f"只有 {len(got)}/{len(ILLU)} 张")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="美术资产验收")
    ap.add_argument("--dump", metavar="DIR", help="另存 2x2 拼接图供人眼复核接缝")
    args = ap.parse_args()

    try:
        from PIL import Image
    except ImportError:
        print("需要 Pillow：python -m pip install pillow（开发工具，不进 requirements）")
        return 2

    print("纹理（可四方连续 + 暗部无色带 + 色相在青/铜两支）")
    for name in TEXTURES:
        path = IMG / name
        if not path.exists():
            check(False, f"{name} 存在")
            continue
        im = Image.open(path)
        seam_abs, seam_ratio = seam_delta(im)
        band = banding_score(im)
        cyan, copper, magenta = hue_split(im)
        print(f"\n  {name}  {im.size[0]}x{im.size[1]}")
        check(im.size[0] == im.size[1], "是正方形（平铺用）", f"{im.size}")
        # 判据：绝对差小到看不见，**或者**比内部纹理差不多（比值接近 1）。
        # 只用比值会把近乎纯黑的图误判成大接缝（内部差≈0，除出来能到 60）。
        check(seam_abs < 1.5 or seam_ratio < 2.0,
              "接缝不明显（绝对差 <1.5 或 接缝差/内部差 <2.0）",
              f"绝对 {seam_abs:.2f} · 比值 {seam_ratio:.2f}")
        check(band <= 2, "暗部无色带（0-64 灰阶空档 ≤2）", f"{band} 个空档")
        spread = texture_spread(im)
        check(spread >= 12, "**上面真的有纹理**（p95−p5 跨度 ≥12）", f"{spread:.1f}")
        check(magenta < 0.08, "没有紫红色相", f"紫红 {magenta:.1%}")
        note("色相分布", f"青 {cyan:.0%} · 铜 {copper:.0%}")

    print("\n横幅（左侧 40% 要留给标题）")
    for name in BANNERS:
        path = IMG / name
        if not path.exists():
            check(False, f"{name} 存在")
            continue
        im = Image.open(path)
        lmean, rmean, l99 = left_clean(im)
        cyan, copper, magenta = hue_split(im)
        print(f"\n  {name}  {im.size[0]}x{im.size[1]}")
        check(round(im.size[0] / im.size[1], 2) == 2.37, "宽幅比例 ≈2.37:1", f"{im.size}")
        check(lmean < rmean, "左侧比右侧暗（标题区在左）", f"左 {lmean:.1f} vs 右 {rmean:.1f}")
        # 白字压在左区上要够对比：左区 99 分位亮度不该超过 ~70/255，
        # 否则那一小块高光会正好顶在标题笔画上
        check(l99 <= 80, "左区没有会顶到标题的高光（99 分位 ≤80）", f"{l99}")
        check(magenta < 0.08, "没有紫红色相", f"紫红 {magenta:.1%}")
        note("色相分布", f"青 {cyan:.0%} · 铜 {copper:.0%}")

    print("\n其余")
    for name in OTHERS:
        path = IMG / name
        if not path.exists():
            check(False, f"{name} 存在")
            continue
        im = Image.open(path)
        cyan, copper, magenta = hue_split(im)
        band = banding_score(im)
        print(f"\n  {name}  {im.size[0]}x{im.size[1]}")
        check(band <= 3, "暗部无色带", f"{band} 个空档")
        check(magenta < 0.08, "没有紫红色相", f"紫红 {magenta:.1%}")
        note("色相分布", f"青 {cyan:.0%} · 铜 {copper:.0%}")

    check_batch2(Image)

    if args.dump:
        out = Path(args.dump)
        if not out.is_absolute():
            out = REPO / out
        out.mkdir(parents=True, exist_ok=True)
        for name in TEXTURES:
            path = IMG / name
            if not path.exists():
                continue
            im = Image.open(path).resize((512, 512))
            tile = Image.new("RGB", (1024, 1024))
            for x in (0, 512):
                for y in (0, 512):
                    tile.paste(im, (x, y))
            tile.save(out / f"tile-{name}")
        print(f"\n2x2 拼接图写到 {out}（人眼复核接缝用）")

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("美术资产验收全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
