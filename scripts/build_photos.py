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
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / ".artsrc" / "photos"
OUT = REPO / "app" / "static" / "img" / "photo"

@dataclass(frozen=True)
class Photo:
    """一张照片的裁切指令。"""

    name: str
    """输出名（不含扩展名）。`core/slots.py` 的 fallback 与模板里引用的就是它。

    **按内容命名，不按用在哪一格命名**（`bench-wide` 而不是 `reason-photo`）——
    照片会换位置，槽位不会跟着改名。
    """

    src: str
    """源文件名。PPT 里的内嵌图编号，保留它是为了能回溯（见 docs/PPT素材清单.md）。"""

    ratio: float
    """目标宽高比。要和用它那一格的 CSS `aspect-ratio` 一致。"""

    anchor_y: float = .5
    """源图比目标「高」时，裁掉的高度怎么分。0=保留顶部 .5=居中 1=保留底部。"""

    anchor_x: float = .5
    """源图比目标「宽」时，裁掉的宽度怎么分。0=保留左边 .5=居中 1=保留右边。

    **这个是后加的。** 原来只有竖向锚点，因为前四张都是横构图裁上下。
    首页「3 个理由」那一格是 4:5 竖版，从 4:3 的源图裁过去要砍掉四成宽度 ——
    居中砍会把左边的信号源和右边的自制板各切一半，正好把这张照片的内容切没了。
    """

    why: str = ""
    """为什么这么裁。下一个人要改构图时能对着看。"""


PHOTOS = [
    Photo("group-2024", "image1.jpeg", 16 / 5, anchor_y=.66, why=
          "约 60 人的全员合影（源图里人从 x=82 铺到 1862，两端几乎没有余量），"
          "所以只能裁上下、不能裁两侧。**从走廊搬到了分镜 02 末尾的整宽合影带**"
          "（home.legacy.group），比例随之从 12/5 放到 16/5：走廊那格宽 432 CSS px，"
          "60 张脸在里面各 7px，那是这张照片最不该出现的尺寸。"
          "锚点 .66 把 1288 高里多出来的 685px 按 452 上 / 233 下分掉 —— 上边缘落在"
          "LED 背景板内部（不带天花板），头顶上方还留着「哈尔滨工程大学」那块字，"
          "脚下留约 100px 反光地面"),
    Photo("group-ti-2025", "image44.jpeg", 4 / 3, why=
          "2025 年 TI 杯全国大学生电子设计竞赛的出征合影，21 人站两排，背景板上"
          "年份与赛事名都在。源图 943x707 本来就是 4:3，一刀都不用裁 —— 走廊"
          "「合影」那一格换成它，接的是搬走的那张全员合影的位置。"
          "选它而不是 image38（2024 省电赛 16 人）的理由是两条：那张是 3:2，裁成 4:3 "
          "要从两侧切掉 106px、正好切到最外侧的人；而且这张更新一年"),
    Photo("award-ti-2024", "image41.jpeg", 4 / 3, why=
          "颁奖台合影：横幅上「2024 年 TI 杯…二等奖」要留住，所以只从两侧裁"),
    Photo("lab-debug", "image42.jpeg", 4 / 3, why=
          "赛场调试：老师 + 三名队员围着示波器。人都在中间"),
    Photo("bench-scopes", "image26.jpg", 16 / 9, anchor_y=.42, why=
          "工作台：两台示波器在上、开发板在下。锚点略偏上 —— "
          "居中裁会把下排板子切掉一半，而「有在用的痕迹」全在那排板子上"),

    # ---- 第二批：换掉首页上那几张不是我们自己拍的图（见 docs/PPT素材清单.md）----
    Photo("bench-wide", "image25.jpg", 4 / 5, why=
          "实验台全景（信号源、936B 焊台、烙铁、铜垫板、一整套自制射频板、元件盒、"
          "钳镊）。去首页「3 个理由」那一格 —— 549x686、骑跨黑白分界线，是全页"
          "视觉权重最高的一处，原来放的是和走廊重复的那张 pcb.webp。"
          "**4:5 要从 4:3 的源图砍掉四成宽度**，所以锚点是这一张最要紧的参数"),
    Photo("rf-modules-board", "image23.jpeg", 16 / 10, why=
          "木板上的射频系统：TI LaunchPad + 多块自制模块 + SMA 互联 + 手写标注。"
          "去三大方向卡 01「硬件工程师」，替掉 img/recruit/oscilloscope.webp"
          "（那是器材图鉴里的棚拍，不是我们自己拍的）"),
    Photo("rf-amp-lcd", "image24.jpeg", 16 / 10, why=
          "亚克力板上的射频宽带放大器：LCD 上有实时参数、一排 LED 亮着、STM32 核心板。"
          "去卡 02「嵌入式开发者」，替掉 img/recruit/board-stm32.webp（源文件就叫"
          " STM32.png，是产品图）—— 屏上有参数才读得出「板子真的在跑」"),
    Photo("contest-inspect", "image43.jpeg", 16 / 10, why=
          "赛场上两名队员在看一块自制 PCB，TI 队服，专业摄影。去卡 03「电赛选手」，"
          "替掉 img/carousel/etched-board.webp（那张同时是走廊 home.gallery.etched "
          "的兜底，一图两用）"),
    Photo("probe-fpga", "image27.jpeg", 16 / 9, why=
          "手持探头在测 FPGA 开发板，Tektronix 屏上是方波。去新生指南的"
          " recruit.software.debug —— 那一格的 brief 要「屏幕上是输出、桌上板子接着"
          "探头、手在画面里」，这张三条都对上了，而它一直是空焊盘"),
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

    missing = [p.src for p in PHOTOS if not (SRC / p.src).exists()]
    if missing:
        print(f"源目录 {SRC}")
        for p in PHOTOS:
            print(f"  {'OK ' if (SRC / p.src).exists() else '缺 '} {p.name:18s} ← {p.src}")
        print(f"\n缺 {len(missing)} 个源文件")
        print("（母图从 PPT 里挖：python scripts/dump_pptx.py，"
              "然后按 docs/PPT素材清单.md 把用到的复制进 .artsrc/photos/）")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    bad = []
    for p in PHOTOS:
        im = Image.open(SRC / p.src).convert("RGB")
        w, h = im.size
        cur = w / h
        if cur > p.ratio:                    # 源更宽 → 裁两侧，按横向锚点
            new_w = round(h * p.ratio)
            left = round((w - new_w) * p.anchor_x)
            im = im.crop((left, 0, left + new_w, h))
        elif cur < p.ratio:                  # 源更高 → 裁上下，按竖向锚点
            new_h = round(w / p.ratio)
            top = round((h - new_h) * p.anchor_y)
            im = im.crop((0, top, w, top + new_h))
        if im.width > MAX_W:
            im = im.resize((MAX_W, round(MAX_W / p.ratio)), Image.LANCZOS)

        dest = OUT / f"{p.name}.webp"
        im.save(dest, "WEBP", quality=QUALITY, method=6)

        # **产物比例必须真的等于声明的比例。** 这不是形式检查：`object-fit: cover`
        # 会把不匹配的部分再裁一次，于是「我以为已经按锚点裁好的构图」在页面上
        # 又被从中心切了一刀 —— 而页面照常渲染、图也没碎，只是构图不是你定的那个。
        got = im.width / im.height
        if abs(got - p.ratio) > 0.01:
            bad.append(f"{p.name}：声明 {p.ratio:.3f}，产物 {got:.3f}")

        print(f"  {p.name:18s} {w}x{h} ({cur:.2f}) → {im.size[0]}x{im.size[1]} "
              f"({got:.2f})  {dest.stat().st_size / 1024:5.0f} KB")
        if p.why:
            print(f"                     {p.why}")

    print(f"\n写到 {OUT.relative_to(REPO)}（{len(PHOTOS)} 张）")
    if bad:
        print("\n**产物比例和声明不一致**：" + "；".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
