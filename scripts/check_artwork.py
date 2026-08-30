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
# 首屏大氛围图：走 `home.css` 里 `.nf-hero::before` 的 `--hero-art` 变量。
# 安全区同样是算出来的：第一屏在桌面是 `min-height: 100vh`（= 视口，1.60~1.78:1）、
# 窄屏是 `min-height: auto`（实测 390x530 = 0.74:1），比例跨度 2.5 倍。
# 4:3 是同时满足两头的那一档，`cover` + `right center` 之下
#   1.78 的屏看到竖向 12.5%~87.5%（整宽）、0.70 的竖屏看到横向 48%~100%（整高）
# 再和 `.nf-hero-overlay` 那两道遮罩留出的窗口（横 62%~100% × 竖 22%~72%）取交集，
# 就是「意象在右 38% × 竖中 50%」，左 58% 留给那条巨字（文字块右边缘在 57%）。
HOME_HERO = "hero-home.webp"

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

    **只在「像素够多」的那一段里数空档。** 第一版拿「第一个有值的灰阶」到
    「最后一个有值的灰阶」当范围，于是**高光尾巴上的稀疏采样会被误判成色带**：
    `tex-etched-copper` 在 52 / 55 / 59 三级各是 0，而它们左右邻居也只有 1~3 个
    像素（那是几个镜面高光点），0~51 那一段密得连一个空档都没有。
    照那样判，任何带一点高光的暗材质都会红。

    门槛取「总像素的两万分之一」：512² 图上约 13 个像素。低于它的灰阶不算
    「这里本该有像素」，所以不参与空档统计。真正的梳齿仍然拦得住 —— 梳齿的两侧
    是**大量**像素，空档夹在它们中间。
    """
    g = im.convert("L")
    hist = g.histogram()[:64]
    floor = max(4, (g.size[0] * g.size[1]) // 20000)
    dense = [i for i, n in enumerate(hist) if n >= floor]
    if len(dense) < 2:
        return 0
    return sum(1 for i in range(dense[0], dense[-1] + 1) if hist[i] == 0)


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


def bright_bbox(im, pct=99.5, trim=2.0):
    """最亮那一小撮像素的外接框（比例坐标）+ 门槛亮度 + 命中像素数。

    这一条是用来钉**构图**的。分区平均值量不出「主体跑到画面中间了」—— 主体在
    正中间时，右区的平均亮度照样很低，六条亮度断言可以全绿而图是废的。而
    「意象」在暗场氛围图里就是画面最亮的那一小块，所以直接量它在哪。

    `trim` 是刻意的：柔光会在整幅画面上撒下零星几个够亮的像素，拿 min/max 取
    外接框会被那几个点撑到全画幅。取 2~98 分位相当于问「亮的那堆**主体**在哪」，
    而不是「有没有一个亮像素跑出去了」。
    """
    import numpy as np

    a = np.asarray(im.convert("L"), dtype=np.float32)
    thr = float(np.percentile(a, pct))
    ys, xs = np.nonzero(a >= thr)
    h, w = a.shape
    if xs.size == 0:          # 全图同一个亮度，谈不上外接框
        return 0.0, 1.0, 0.0, 1.0, thr, 0
    return (float(np.percentile(xs, trim)) / w,
            float(np.percentile(xs, 100 - trim)) / w,
            float(np.percentile(ys, trim)) / h,
            float(np.percentile(ys, 100 - trim)) / h,
            thr, int(xs.size))


def subject_lift(im, x0f=0.60) -> float:
    """意象区的 99.9 分位亮度比全图中位数高多少。

    回答的是「画面里到底有没有一个主体」。用分位数而不是最大值：最大值只要一个
    亮像素就能满足，而 99.9 分位要求意象区里有千分之一的面积真的亮起来。
    校准数据见 check_batch3 里那段注释。
    """
    import numpy as np

    a = np.asarray(im.convert("L"), dtype=np.float32)
    right = a[:, int(a.shape[1] * x0f):]
    return float(np.percentile(right, 99.9) - np.median(a))


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
        # ---- 这一条是无障碍守卫，不是审美判断 ----
        # 材质铺满白区之后，**文字实际压着的底色就是这张图**，不再是 #f7f8fa。
        # 而 `check_a11y.py` 量的是元素自己的 `background-color`（材质画在
        # ::before 上，不在它那条链上），所以它永远量到 248、永远是绿的。
        #
        # 白区最紧的角色是 eyebrow 小字（13px，`--accent-ink` #0a7288，要 4.5:1）。
        # 量**最暗的 5%** 而不是中位数：纹理是逐像素变化的，笔画正好落在暗纹上的
        # 情况必须也过关。实测 #0a7288 在 230 的底色上是 4.55:1，所以门槛取 230。
        #
        # 这条断言和 `--accent-ink` 是一对：谁改了另一个也要重算。
        # 第二版母图（平均 236.5、p5 约 223）就是踩在这条线下面 —— 铺上去之后
        # eyebrow 跌到 4.4，而全套浏览器脚本一条都不会红。
        import numpy as np
        p5 = float(np.percentile(np.asarray(im.convert("L"), dtype=np.float32), 5))
        check(p5 >= 230,
              "**白区文字压上去仍够对比**（最暗 5% ≥230 ⇔ eyebrow 有 4.5:1）",
              f"{p5:.0f}")
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


def check_batch3(Image) -> None:
    """首屏大氛围图。工单在 docs/美术资产清单.md 的「第三批」一节。

    和第二批同样：**缺文件不算失败**，只打印「待交付」。
    """
    print("\n第三批 · 首屏大氛围图（意象在右 38% × 竖中 50%，左 58% 留给巨字）")
    path = IMG / HOME_HERO
    if not path.exists():
        pending(HOME_HERO, "首页第一屏")
        return
    im = Image.open(path)
    ratio = im.size[0] / im.size[1]
    lmean, l99, _ = region(im, 0.0, 0.58)
    rmean, r99, _ = region(im, 0.62, 1.0)
    _, _, g999 = region(im, 0.0, 1.0)
    bx0, bx1, by0, by1, thr, npx = bright_bbox(im)
    cyan, copper, magenta = hue_split(im)
    print(f"\n  {HOME_HERO}  {im.size[0]}x{im.size[1]}  首页第一屏")
    check(1.30 <= ratio <= 1.37,
          "比例 ≈4:3（0.70~1.78 两头都能裁到安全区的那一档）",
          f"{ratio:.3f}  {im.size}")
    check(l99 <= 30, "左 58% 干净（99 分位 ≤30，那是巨字的地盘）", f"{l99:.0f}")
    check(lmean < rmean, "左侧比右侧暗", f"左 {lmean:.1f} vs 右 {rmean:.1f}")
    # 窄屏上 hero 只有 530 高而文字铺满整宽（实测 x 16~374 / 390），巨字是直接
    # 压在意象上的。所以这两条是无障碍守卫，不是审美判断 —— 同第二批页头。
    check(rmean <= 25, "右 38% 整体仍是暗场（平均 ≤25，窄屏时巨字压在这一区上）",
          f"{rmean:.1f}")
    # 比第二批页头的 ≤140 紧一档，因为窄屏上这张图被放大约 2.9 倍（源 45%~100%
    # 铺满 390 宽），意象会挤到屏幕中部、压在**导语**上 —— 而导语是 `--muted`，
    # 要 4.5:1 就要求底色 ≤57，比巨字（大字号，3:1，上限 149）紧得多。
    # 118 是「白字 4.5:1」那条线；配上窄屏那道 .55 压暗（见 home.css 的 720px 块）
    # 落到 53，压在导语那条线以内。这两个数是一对。
    check(r99 <= 118, "右 38% 没有大片过曝（99 分位 ≤118）", f"{r99:.0f}")
    check(g999 <= 210, "全图 99.9 分位 ≤210（细高光可以，大面积不行）", f"{g999:.0f}")
    # 先确认被测的东西真的出现了：一片均匀近黑能让上面每一条亮度断言都过 ——
    # T4 阻焊哑光面就是那样交付的（压完只有 2KB，「极细微质感」被理解成纯黑）。
    #
    # 阈值是在**已上线的七张页头图（阳性）+ 人造废图（阴性）**上校准出来的，
    # 不是拍脑袋（`.shots/calib.py` 那次量的）：
    #   右区 p99.9 − 全图中位数   阳性 52~150   阴性 0~3    ← 用这个，间隔 49
    #   最大值 − 中位数           阳性 154~253  阴性 0~4    间隔更大但只看单个像素，
    #                                                     一个亮点就能骗过去
    #   p95−p5（纹理那条的判据）  阳性 3~7      阴性 0~3    **间隔 0，完全无效**
    # 最后一条要记住：氛围图 99% 的面积按设计就是黑的，跨度类统计量在这里没有
    # 分辨力。别把纹理那条判据搬过来。
    lift = subject_lift(im)
    check(lift >= 30,
          "**画面里真有一个意象**（右区 p99.9 比全图中位数高 ≥30）", f"高出 {lift:.0f}")
    check(bx0 >= 0.55 and by0 >= 0.15 and by1 <= 0.80,
          "**意象落在安全窗口内**（横 55%~100% × 竖 15%~80%）",
          f"横 {bx0:.0%}~{bx1:.0%} · 竖 {by0:.0%}~{by1:.0%}")
    check(magenta < 0.08, "没有紫红色相", f"紫红 {magenta:.1%}")
    note("最亮 0.5%", f"{npx} 个像素")
    note("色相分布", f"青 {cyan:.0%} · 铜 {copper:.0%}")


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
    check_batch3(Image)

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
