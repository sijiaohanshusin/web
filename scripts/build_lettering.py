# -*- coding: utf-8 -*-
"""科协专属数字：把数字当电路板走线画出来，并打包成一款只含数字的字体。

## 为什么是数字，为什么是字体

先试过用同一套走线语言做整句汉字标题（一、个、电都很漂亮），但**等宽走线放不下
10 笔以上的字**：「想」13 笔要 7 条平行横画，96px 的字面里 8px 墨 + 8px 缝 × 7
= 112px，比字面本身还高，只能糊成一团。这是物理约束。
数字反过来 —— 一个数字最多 3~4 笔，走线语言正好合适，而这个站到处是大数字
（分镜 02 的「31」、报名人数、荣誉统计、倒计时、分镜编号）。

**做成字体而不是 SVG 图**，因为那些数字大多不是静态的：分镜 02 的大数字由 JS 从 0
计到目标值、倒计时每秒重写、统计数字来自数据库。SVG 图片没法参与这些。

## 构造语言（和 `brand/logo-mark.svg` 同一套）

    走线宽     96 / 1000 em
    焊盘环     外径 168，环宽 88（内孔直径 80）
    转角       只走 0° / 90° / 45°，转角 45° 斜切
    等宽       所有数字同一个字宽 620，否则计数器每跳一位就抖一下

两条从会标继承的硬规则：走线**止于焊盘环外缘**（画到圆心会把内孔填掉，焊盘就变成
实心点）；焊盘是标点不是装饰 —— 每个数字最多一个，落在「笔画在空处收尾」的地方。

## 轮廓是怎么来的（没有布尔运算）

字体没有「描边」概念，所以要把走线变成填充轮廓。做法是纯几何、不需要布尔求并：

- 每一段走线 = 一个四边形（沿法线偏移半个线宽）
- 每个折点与端点 = 一个正八边形（半径 = 半线宽），当作圆角接头与圆头端点
- 焊盘环 = 外圆 + **反向**内圆

这些轮廓互相重叠，而字体用非零环绕规则填充：**同向重叠自动求并，反向的内圆就是孔**。
所以不需要 pathops，也不会因为布尔运算的数值误差产生毛刺。

跑法：
    python scripts/build_lettering.py --preview .shots/digits   # 出 SVG 预览页
    python scripts/build_lettering.py --font                     # 出 woff2 进 static/fonts
"""
import argparse
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FONT_OUT = REPO / "app" / "static" / "fonts" / "ESTADigits.woff2"

UPM = 1000          # units per em
FIG = 700           # 数字高度（基线到顶）
ADV = 570           # 数字字宽（等宽 —— 计数器每跳一位不能抖）
TRACE = 96          # 走线宽
PAD_R = 84          # 焊盘环外半径
PAD_HOLE = 40       # 焊盘内孔半径
PAD_STOP = 104      # 走线在距焊盘圆心多远处收笔（略大于外半径，压在环上）
# 转角斜切长度。不能取得和线宽同一个量级：数字里为了逼近弧线用了一串密排转角，
# 斜切一长，相邻两刀就快接上了，笔画之间只剩很短的直段 —— 边缘一路凹凸，
# 读起来是「手画歪了」而不是「精密走线」。取 38 让每一刀都干脆、直段足够长。
CHAMFER = 38
KAPPA = 0.5522847498  # 用三次贝塞尔拟合圆弧的常数

# ---------------------------------------------------------------- 字形数据
# 每个字形：strokes（走线折线）+ pads（焊盘圆心）+ advance（字宽）。
# 坐标是字体坐标系：x 向右，y 向上，基线 y=0，数字顶 y=700。
# 折线的每一段必须是水平、垂直或正 45°（写完用 --check 验）。
GLYPHS: dict[str, dict] = {
    # 0：一圈闭合走线（八角环）。闭合形状没有「空处收尾」，所以不放焊盘。
    "0": {"strokes": [{"pts": [(130, 0), (490, 0), (490, 700), (130, 700)], "closed": True}]},

    # 1：主竖 + 45° 起笔撇 + 底座。
    # 焊盘放在**撇的自由端**，不放在顶端 —— 放顶端时它和撇挤在一个角上糊成一团，
    # 而放在撇尾读作「信号从这里进来，拐下去，走到底座」。
    "1": {
        "strokes": [
            {"pts": [(310, 0), (310, 700)]},
            {"pts": [(310, 700), (140, 530)], "pads": ["end"]},
            {"pts": [(130, 0), (490, 0)]},
        ],
    },
    # 2：上弧 → 45° 长斜线下来 → 底横。一笔到底。
    "2": {
        "strokes": [{"pts": [
            (130, 480), (130, 590), (240, 700), (380, 700), (490, 590), (490, 480),
            (130, 120), (130, 0), (490, 0),
        ], "pads": ["start"]}],
    },
    # 3：两个碗，中腰向左收一刀
    "3": {
        "strokes": [{"pts": [
            (130, 590), (240, 700), (380, 700), (490, 590), (490, 470), (400, 380),
            (490, 290), (490, 110), (380, 0), (240, 0), (130, 110),
        ], "pads": ["start"]}],
    },
    # 4：45° 斜线 + 横担 + 竖。
    # 焊盘放在横担左端，**不放在竖的下端** —— 放下端时焊盘环有一半掉到基线以下，
    # 整个数字看起来长了个尾巴，一行数字的基线也就跟着乱了。
    "4": {
        "strokes": [
            {"pts": [(430, 700), (140, 410)]},
            {"pts": [(100, 410), (540, 410)], "pads": ["start"]},
            {"pts": [(430, 700), (430, 0)]},
        ],
    },
    # 5：顶横 → 左竖 → 中横 → 45° 拐下 → 下碗
    "5": {
        "strokes": [{"pts": [
            (490, 700), (130, 700), (130, 410), (370, 410), (490, 290), (490, 110),
            (380, 0), (240, 0), (130, 110),
        ], "pads": ["start"]}],
    },
    # 6：上弧下来 + 闭合的下碗
    "6": {
        "strokes": [{"pts": [
            (470, 590), (360, 700), (240, 700), (130, 590), (130, 110), (240, 0),
            (380, 0), (490, 110), (490, 250), (380, 360), (240, 360), (130, 250),
        ], "pads": ["start"]}],
    },
    # 7：顶横 → 45° 拐一下 → 直下。真实 7 的斜线比 45° 陡，
    #    而这套字只允许 45°，所以改成「拐 45° 再直下」—— 正好是 PCB 布线的样子。
    #    焊盘放在顶横的起点（同 4 的理由：放竖的下端会掉到基线以下）。
    "7": {
        "strokes": [{"pts": [
            (130, 700), (490, 700), (490, 560), (300, 370), (300, 0),
        ], "pads": ["start"]}],
    },
    # 8：上下两个闭合环，上窄下宽（和真实 8 的比例一致）
    "8": {
        "strokes": [
            {"pts": [(170, 360), (450, 360), (450, 700), (170, 700)], "closed": True},
            {"pts": [(130, 0), (490, 0), (490, 360), (130, 360)], "closed": True},
        ],
    },
    # 9：6 的 180° 旋转
    "9": {
        "strokes": [{"pts": [
            (150, 110), (260, 0), (380, 0), (490, 110), (490, 590), (380, 700),
            (240, 700), (130, 590), (130, 450), (240, 340), (380, 340), (490, 450),
        ], "pads": ["start"]}],
    },

    # ---- 记号 ----
    # 小数点与冒号就是焊盘本身 —— 站上的「点」本来就是焊盘这个语言。
    ".": {"strokes": [], "pads_free": [(150, 84)], "advance": 300},
    ":": {"strokes": [], "pads_free": [(150, 160), (150, 520)], "advance": 300},
    "+": {
        "strokes": [{"pts": [(80, 350), (460, 350)]}, {"pts": [(270, 160), (270, 540)]}],
        "advance": 540,
    },
    "-": {"strokes": [{"pts": [(80, 350), (460, 350)]}], "advance": 540},
    "/": {"strokes": [{"pts": [(90, 0), (530, 440)]}], "advance": 620},
    "%": {
        "strokes": [{"pts": [(120, 60), (620, 560)]}],
        "pads_free": [(150, 560), (590, 60)],
        "advance": 740,
    },
    " ": {"strokes": [], "advance": 300},
}


# ---------------------------------------------------------------- 几何
def chamfered(pts: list[tuple[float, float]], closed: bool) -> list[tuple[float, float]]:
    """把折线的每个内部顶点换成两个点，做出 45° 斜切转角。

    斜切长度不能超过相邻边长的一半，否则短边上会把线段翻过来。
    """
    n = len(pts)
    out: list[tuple[float, float]] = []
    idx = range(n) if closed else range(1, n - 1)
    if not closed:
        out.append(pts[0])
    for i in idx:
        cur = pts[i]
        prev = pts[(i - 1) % n]
        nxt = pts[(i + 1) % n]
        for other in (prev, nxt):
            dx, dy = other[0] - cur[0], other[1] - cur[1]
            length = math.hypot(dx, dy)
            if length == 0:
                continue
            cut = min(CHAMFER, length / 2)
            out.append((cur[0] + dx / length * cut, cur[1] + dy / length * cut))
    if not closed:
        out.append(pts[-1])
    return out


def trim_to_pad(pts: list[tuple[float, float]], which: str) -> list[tuple[float, float]]:
    """把某一端收到距端点 PAD_STOP 处 —— 走线止于焊盘环外缘，不进内孔。"""
    p = list(pts)
    i, j = (0, 1) if which == "start" else (-1, -2)
    ax, ay = p[i]
    bx, by = p[j]
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length <= PAD_STOP:
        raise SystemExit(f"焊盘那一段太短（{length:.0f} < {PAD_STOP}），收笔后会没有走线")
    t = PAD_STOP / length
    p[i] = (ax + dx * t, ay + dy * t)
    return p


def resolve(spec: dict) -> tuple[list[list[tuple[float, float]]], list[tuple[float, float]]]:
    """把字形数据展开成「折线列表 + 焊盘圆心列表」。"""
    lines: list[list[tuple[float, float]]] = []
    pads: list[tuple[float, float]] = list(spec.get("pads_free", []))
    for stroke in spec["strokes"]:
        pts = list(stroke["pts"])
        for which in stroke.get("pads", []):
            pads.append(pts[0] if which == "start" else pts[-1])
            pts = trim_to_pad(pts, which)
        lines.append(chamfered(pts, stroke.get("closed", False)) +
                     ([chamfered(pts, True)[0]] if stroke.get("closed") else []))
    return lines, pads


def check_angles() -> list[str]:
    """每一段必须是水平、垂直或正 45°。这是这套字的构造规则，值得被钉住。"""
    bad: list[str] = []
    for char, spec in GLYPHS.items():
        for k, stroke in enumerate(spec["strokes"]):
            pts = stroke["pts"]
            seq = pts + [pts[0]] if stroke.get("closed") else pts
            for (x1, y1), (x2, y2) in zip(seq, seq[1:]):
                dx, dy = abs(x2 - x1), abs(y2 - y1)
                ok = dx < 0.5 or dy < 0.5 or abs(dx - dy) < 0.5
                if not ok:
                    bad.append(f"{char} 第 {k} 笔 ({x1},{y1})->({x2},{y2}) "
                               f"不是 0/90/45（dx={dx:.0f} dy={dy:.0f}）")
    return bad


# ---------------------------------------------------------------- SVG 预览
def svg_glyph(char: str, spec: dict) -> str:
    lines, pads = resolve(spec)
    adv = spec.get("advance", ADV)
    body = []
    for pts in lines:
        d = "M " + " L ".join(f"{x:.0f} {UPM - y:.0f}" for x, y in pts)
        body.append(f'<path d="{d}" />')
    for cx, cy in pads:
        body.append(f'<circle cx="{cx:.0f}" cy="{UPM - cy:.0f}" '
                    f'r="{(PAD_R + PAD_HOLE) / 2:.0f}" stroke-width="{PAD_R - PAD_HOLE}" />')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 {UPM - FIG - 60} {adv} {FIG + 120}" '
            f'fill="none" stroke="currentColor" stroke-width="{TRACE}" '
            f'stroke-linecap="round" stroke-linejoin="round" role="img" aria-label="{char}">'
            + "".join(body) + "</svg>")


# ---------------------------------------------------------------- 字体
def add_circle(pen, cx: float, cy: float, r: float, ccw: bool = False) -> None:
    """用四段三次贝塞尔画一个圆。ccw=True 时反向 —— 反向的圆就是孔。"""
    k = r * KAPPA
    pts = [
        ((cx, cy + r), (cx + k, cy + r), (cx + r, cy + k), (cx + r, cy)),
        ((cx + r, cy), (cx + r, cy - k), (cx + k, cy - r), (cx, cy - r)),
        ((cx, cy - r), (cx - k, cy - r), (cx - r, cy - k), (cx - r, cy)),
        ((cx - r, cy), (cx - r, cy + k), (cx - k, cy + r), (cx, cy + r)),
    ]
    if ccw:
        pts = [(a, c, b, s) for (s, b, c, a) in reversed(pts)]
    pen.moveTo(pts[0][0])
    for _, c1, c2, end in pts:
        pen.curveTo(c1, c2, end)
    pen.closePath()


def add_poly(pen, poly: list[tuple[float, float]]) -> None:
    pen.moveTo(poly[0])
    for p in poly[1:]:
        pen.lineTo(p)
    pen.closePath()


def draw_glyph(pen, spec: dict) -> None:
    """走线 → 填充轮廓：每段一个四边形，每个节点一个八边形（当圆角接头/圆头端点）。

    全部同向重叠，非零环绕自动求并；焊盘的内圆反向，于是成为孔。
    """
    lines, pads = resolve(spec)
    half = TRACE / 2
    for pts in lines:
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            dx, dy = x2 - x1, y2 - y1
            length = math.hypot(dx, dy)
            if length < 1e-6:
                continue
            nx, ny = -dy / length * half, dx / length * half
            add_poly(pen, [(x1 + nx, y1 + ny), (x2 + nx, y2 + ny),
                           (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)])
        for x, y in pts:
            # 接头/端点用一个正多边形当圆角。两个容易做错的地方：
            #
            # 1. **绕向必须和四边形一致（顺时针）。** 角度递增画出来是逆时针，
            #    而非零环绕下逆时针叠在顺时针上会互相抵消 —— 每个接头都被打成
            #    一个孔，字看起来像被虫蛀了。所以 reversed。
            # 2. **多边形要外切，不是内切。** 顶点取半径 = 半线宽时，边落在
            #    半径 × cos(π/n) 上，比走线还窄 —— 于是转角外侧填不满、顶点又
            #    支出来，笔画边缘一路凹凸（280px 上一眼看得见）。
            #    顶点半径除以 cos(π/n) 让边正好压在半线宽上；n 取 16，
            #    顶点外凸只剩 2%。
            r = half / math.cos(math.pi / 16)
            add_poly(pen, list(reversed(
                [(x + r * math.cos(a), y + r * math.sin(a))
                 for a in [math.pi / 16 + math.pi / 8 * i for i in range(16)]])))
    for cx, cy in pads:
        add_circle(pen, cx, cy, PAD_R)
        add_circle(pen, cx, cy, PAD_HOLE, ccw=True)


def build_font() -> None:
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen

    names = {
        "familyName": "ESTA Digits",
        "styleName": "Regular",
        "psName": "ESTADigits-Regular",
        "version": "1.0",
        "copyright": "HEU ESTA. Geometry generated by scripts/build_lettering.py.",
        "manufacturer": "HEU ESTA",
    }
    order = [".notdef"] + [f"g{ord(c):04X}" for c in GLYPHS]
    cmap = {ord(c): f"g{ord(c):04X}" for c in GLYPHS}

    fb = FontBuilder(UPM, isTTF=False)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)

    charstrings = {}
    metrics = {".notdef": (ADV, 0)}
    pen = T2CharStringPen(ADV, None)
    pen.moveTo((0, 0))
    pen.closePath()
    charstrings[".notdef"] = pen.getCharString()
    for char, spec in GLYPHS.items():
        adv = spec.get("advance", ADV)
        gpen = T2CharStringPen(adv, None)
        draw_glyph(gpen, spec)
        name = f"g{ord(char):04X}"
        charstrings[name] = gpen.getCharString()
        metrics[name] = (adv, 0)

    fb.setupCFF(names["psName"], {"FullName": "ESTA Digits"}, charstrings, {})
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=FIG + 60, descent=-120)
    fb.setupNameTable(names)
    fb.setupOS2(sTypoAscender=FIG, sTypoDescender=-120, usWinAscent=FIG + 60,
                usWinDescent=120, sxHeight=FIG, sCapHeight=FIG)
    fb.setupPost()
    fb.font.flavor = "woff2"
    FONT_OUT.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(FONT_OUT))
    print(f"  {FONT_OUT.relative_to(REPO)}  {FONT_OUT.stat().st_size / 1024:.0f} KB  "
          f"{len(GLYPHS)} 个字形")


def write_preview(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cells = []
    for char, spec in GLYPHS.items():
        if char == " ":
            continue
        cells.append(f'<div class="cell"><div class="g">{svg_glyph(char, spec)}</div>'
                     f'<span class="n">{char}</span></div>')
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>科协数字</title>
<style>
 body {{ background:#050506; color:#e9edf4; font-family:Consolas,monospace; padding:26px 34px; }}
 h1 {{ font-size:13px; letter-spacing:2px; color:#e2ab63; font-weight:400; margin:0 0 18px; }}
 .row {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:26px; }}
 .cell {{ text-align:center; }}
 .g {{ width:130px; height:190px; color:#41d8e8; }}
 .g svg {{ width:100%; height:100%; }}
 .n {{ font-size:11px; color:#97a1b3; }}
 .small .g {{ width:52px; height:76px; }}
 .grid .g {{ background-image:
    linear-gradient(rgba(65,216,232,.14) 1px, transparent 1px),
    linear-gradient(90deg, rgba(65,216,232,.14) 1px, transparent 1px);
    background-size:15.6px 15.6px; }}
</style></head><body>
<h1>科协专属数字 · 走线 + 焊盘 · 只走 0/90/45</h1>
<div class="row grid">{''.join(cells)}</div>
<div class="row small">{''.join(cells)}</div>
</body></html>"""
    (out_dir / "index.html").write_text(html, encoding="utf-8", newline="\n")
    print(f"  预览页 {(out_dir / 'index.html').relative_to(REPO)}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="科协专属数字")
    ap.add_argument("--preview", metavar="DIR", help="生成 SVG 预览页到这个目录")
    ap.add_argument("--font", action="store_true", help="生成 woff2 到 app/static/fonts/")
    args = ap.parse_args()

    bad = check_angles()
    if bad:
        print(f"{len(bad)} 段不符合 0/90/45 规则：")
        for b in bad:
            print(f"  - {b}")
        return 1
    print(f"OK   {len(GLYPHS)} 个字形，所有线段都是 0/90/45")

    if args.preview:
        out = Path(args.preview)
        write_preview(out if out.is_absolute() else REPO / out)
    if args.font:
        build_font()
    if not args.preview and not args.font:
        print("（没指定 --preview / --font，只跑了规则检查）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
