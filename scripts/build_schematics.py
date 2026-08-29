# -*- coding: utf-8 -*-
"""原理图片段生成脚本（D4）。把符号库拼成能讲得通的小电路。

产出：`app/static/brand/schem/*.svg` —— 新生指南「电路图与电路板」那一节用。

为什么要拼而不是画
------------------
符号库（`build_symbols.py`）里每个符号都记了 `data-terminals`。拼装读它，
于是「引线接到哪」这件事有唯一事实来源，不靠眼睛对齐。手画一张原理图，
线差两个像素没接上，肉眼看不出来 —— 而那正是**电路图讲不通**的样子。

**电气必须讲得通。** 这是电子科技协会的站：一张接错的原理图比没有图更糟，
新手会照着它接。所以每个片段都要**声明期望网表**（哪些引脚应该在同一个节点上），
生成时把网表写进 SVG 的 `data-nets`，`check_schematics.py` 再从**几何**
重新算一遍连通性和它比对。声明和画法不一致就判红。

坐标系与栅格
------------
片段画布统一 **240x184**，栅格步长 8（符号库是 4，这里放粗一档，
因为原理图的线要拉得开才好读）。画布统一是为了让一排片段的线宽一致 ——
和符号库那条教训一样（高度不统一 = 缩放比例不统一 = 线宽看起来不一样粗）。

放置用「符号中心 + 旋转」：`rotate(90)` 在 SVG 的 y 向下坐标系里是顺时针，
把 (x,y) 映射到 (-y,x)，所以两端元件的第一个端子（本来在左）转到**上方**。

跑法：
    python scripts/build_schematics.py
    python scripts/build_schematics.py --sheet    # 联系表，人眼复核
"""
import argparse
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
OUT = REPO / "app" / "static" / "brand" / "schem"

from build_symbols import STROKE, build_data  # noqa: E402

GRID = 8
# 画布统一 240x240。第一版给 240x184，而竖排的那两张放不下：
# vcc 的符号从端子往上占 24、两个两端元件各 56、gnd 往下占 24，加上给标注的余量
# 就超过 184 了 —— 硬塞的结果是电源符号被上边缘切掉。
# 统一成正方形而不是「每张按需给尺寸」，理由同符号库：一排片段按同一宽度渲染，
# 画布不统一 = 缩放比例不统一 = 线宽看起来不一样粗。
BOX = (240, 240)
SYMS = {s["name"]: s for s in build_data()}


def place_terminals(sym_name, cx, cy, rot):
    """一个符号放到 (cx,cy)、转了 rot 度之后，它的端子在哪。"""
    s = SYMS[sym_name]
    w, h = s["box"]
    a = math.radians(rot)
    ca, sa = round(math.cos(a)), round(math.sin(a))
    pts = []
    for tx, ty in s["terminals"]:
        lx, ly = tx - w / 2, ty - h / 2
        pts.append((cx + lx * ca - ly * sa, cy + lx * sa + ly * ca))
    return pts


def transform(sym_name, cx, cy, rot):
    w, h = SYMS[sym_name]["box"]
    return (f"translate({cx} {cy}) rotate({rot}) "
            f"translate({-w / 2} {-h / 2})")


# ---------------------------------------------------------------------------
# 四个片段。选这四个不是随手挑的 —— 它们分别对应新生指南里已经有的四个元件块，
# 而且是「第一年一定会遇到」的四个：
#   led-series  第一个会接的电路（也是「为什么 LED 要串电阻」的答案）
#   divider     欧姆定律的第一个应用，元件块里写了 V = I x R
#   rc-lowpass  电容块里写了「用于滤波」，这就是那个滤波
#   follower    运放块里写了「接入适当的反馈网络」，这是最简单的那个网络
# ---------------------------------------------------------------------------
def build_frags():
    F = []

    # 端子落在哪是**算出来的，不是估的**（第一版全是估的，七处接不上）：
    #   两端元件 56x48、端子在 (0,24)/(56,24) → 居中后 (∓28, 0)
    #     rot=0  → (cx∓28, cy)        rot=90 → (cx, cy∓28)
    #   vcc 32x48、端子 (16,48) → 居中 (0, 24) → rot=0 时 (cx, cy+24)
    #   gnd 32x48、端子 (16, 0) → 居中 (0,−24) → rot=0 时 (cx, cy−24)
    #   opamp 56x48、端子 (0,12)/(0,36)/(56,24) → 居中 (−28,−12)/(−28,12)/(28,0)
    # 竖排时相邻元件的端子**正好重合**，所以不需要连线段 —— 引线本身就接上了。
    # `connectivity()` 按坐标合并引脚，重合即同一节点。

    # ---- ① LED 限流 ----------------------------------------------------
    # 竖着串：电流从上往下，和「电源在上、地在下」的惯例一致。
    xc = 120
    F.append({
        "name": "led-series", "title": "LED 限流",
        "caption": "LED 自己不限流，直接接电源会烧。串一个电阻把电流压到它能"
                   "承受的范围 —— 第一次点亮 LED 就是这个电路。",
        "parts": [("V1", "vcc", (xc, 32), 0),        # 端子 (120, 56)
                  ("R1", "resistor", (xc, 84), 90),  # 端子 (120, 56) (120, 112)
                  ("D1", "led", (xc, 140), 90),      # 端子 (120,112) (120, 168)
                  ("G1", "gnd", (xc, 192), 0)],      # 端子 (120,168)
        "wires": [],
        # D1 的标注要躲开 LED 的发光箭头（转 90° 之后箭头朝右下），所以往右让 8
        "labels": [("VCC", (xc, 16), "middle"),
                   ("R1", (xc + 20, 88), "start"),
                   ("D1", (xc + 28, 152), "start")],
        "nets": {"VCC": ["V1.1", "R1.1"],
                 "N1": ["R1.2", "D1.1"],
                 "GND": ["D1.2", "G1.1"]},
    })

    # ---- ② 电阻分压 ----------------------------------------------------
    xd = 88
    F.append({
        "name": "divider", "title": "电阻分压",
        "caption": "两个电阻串起来，中间那点的电压按阻值比例分："
                   "Vout = VCC × R2 ÷ (R1 + R2)。欧姆定律的第一个用处。",
        "parts": [("V1", "vcc", (xd, 32), 0),
                  ("R1", "resistor", (xd, 84), 90),
                  ("R2", "resistor", (xd, 140), 90),
                  ("G1", "gnd", (xd, 192), 0)],
        # 中点 (88,112) 引出去。它同时是 R1.2 与 R2.1 所在的点，
        # 于是那里有三样东西汇合 —— render() 会自动画连接点。
        "wires": [[(xd, 112), (184, 112)]],
        "labels": [("VCC", (xd, 16), "middle"),
                   ("R1", (xd + 20, 88), "start"),
                   ("R2", (xd + 20, 144), "start"),
                   ("Vout", (188, 116), "start")],
        "nets": {"VCC": ["V1.1", "R1.1"],
                 "MID": ["R1.2", "R2.1"],
                 "GND": ["R2.2", "G1.1"]},
    })

    # ---- ③ RC 低通滤波 -------------------------------------------------
    # 横向信号路 + 一个并到地的电容。
    # 输出那条线**必须在分岔点断开成两段**：`connectivity()` 只按端点重合判
    # 连通（原理图的规则就是这样），一条从 124 直通 208 的线不会和 (152,88)
    # 处引下来的那条接上 —— 而画面上看起来是接上的。这正是要拦的那类错。
    F.append({
        "name": "rc-lowpass", "title": "RC 低通滤波",
        "caption": "电阻串在信号路上、电容并到地。高频被电容旁路掉、低频照常"
                   "通过 —— 电容「阻直流、通交流」最直接的用法。",
        "parts": [("R1", "resistor", (96, 88), 0),      # 端子 (68,88) (124,88)
                  ("C1", "capacitor", (152, 144), 90),  # 端子 (152,116) (152,172)
                  ("G1", "gnd", (152, 196), 0)],        # 端子 (152,172)
        "wires": [[(24, 88), (68, 88)],
                  [(124, 88), (152, 88)],
                  [(152, 88), (208, 88)],
                  [(152, 88), (152, 116)]],
        "labels": [("Vin", (20, 92), "end"),
                   ("Vout", (212, 92), "start"),
                   ("R1", (96, 68), "middle"),
                   ("C1", (172, 148), "start")],
        "nets": {"IN": ["R1.1"],
                 "OUT": ["R1.2", "C1.1"],
                 "GND": ["C1.2", "G1.1"]},
    })

    # ---- ④ 运放电压跟随器 ----------------------------------------------
    # opamp 端子：1 = (0,12) 反相输入 −、2 = (0,36) 同相输入 +、3 = (56,24) 输出。
    # 跟随器 = 输出直接接回反相输入。反馈线绕**上方**走（惯例），
    # 而且必须绕开三角本体：三角在 y 92~132、x 106~134，反馈横段走 y=56。
    F.append({
        "name": "follower", "title": "运放电压跟随器",
        "caption": "输出直接接回反相输入，于是输出跟着输入走、增益是 1。"
                   "看着没做事，其实把带不动负载的高阻信号变成了能带负载的信号。",
        "parts": [("U1", "opamp", (120, 112), 0)],
        # U1.1 (92,100) 反相  U1.2 (92,124) 同相  U1.3 (148,112) 输出
        "wires": [[(24, 124), (92, 124)],
                  [(148, 112), (184, 112)],
                  [(184, 112), (208, 112)],
                  [(184, 112), (184, 56), (68, 56), (68, 100), (92, 100)]],
        "labels": [("Vin", (20, 128), "end"),
                   ("Vout", (212, 116), "start"),
                   ("U1", (120, 152), "middle")],
        "nets": {"IN": ["U1.2"],
                 "OUT": ["U1.3", "U1.1"]},
    })
    return F


# ---------------------------------------------------------------------------
def pins_of(frag):
    """片段里所有引脚的绝对坐标：{"R1.1": (x,y), ...}"""
    pins = {}
    for ref, sym, (cx, cy), rot in frag["parts"]:
        for i, p in enumerate(place_terminals(sym, cx, cy, rot), start=1):
            pins[f"{ref}.{i}"] = p
        assert sym in SYMS, sym
    return pins


def connectivity(pins, wires, eps=0.75):
    """从几何算连通性：引脚与线段端点按坐标合并，返回若干个节点（引脚名集合）。

    只按**端点重合**判连通 —— 这正是原理图的规则：线要接到引脚上，
    差一点就是没接上。刻意不做「点落在线段中间也算连上」的推断：
    那种画法（T 形接点没画节点）在真实原理图里本来就该显式画连接点，
    所以这里也要求显式：需要三条线交汇时，就让两条线共用一个端点。
    """
    parent = {}

    def key(p):
        return (round(p[0] / eps), round(p[1] / eps))

    def find(a):
        while parent.setdefault(a, a) != a:
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for w in wires:
        for a, b in zip(w, w[1:]):
            union(key(a), key(b))
        # 单点「线」（长度 0）表示两个端子直接重合，上面的 zip 会退化成空，
        # 这里补一次自并，保证这个坐标进入并查集
        union(key(w[0]), key(w[0]))
    for name, p in pins.items():
        union(key(p), key(p))

    groups = {}
    for name, p in pins.items():
        groups.setdefault(find(key(p)), set()).add(name)
    return list(groups.values())


HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        'fill="none" stroke="currentColor" stroke-width="{sw}" '
        'stroke-linecap="round" stroke-linejoin="round" '
        'data-nets="{nets}">')


def render(frag) -> str:
    w, h = BOX
    pins = pins_of(frag)
    nets = ";".join(f"{k}={','.join(sorted(v))}"
                    for k, v in sorted(frag["nets"].items()))
    out = [HEAD.format(w=w, h=h, sw=STROKE, nets=nets),
           f'  <title>{frag["title"]}原理图</title>']

    # 连线
    for wire in frag["wires"]:
        if len(wire) < 2 or all(p == wire[0] for p in wire):
            continue                     # 长度 0 的「线」只是声明两端子重合
        d = "M" + "L".join(f"{x} {y}" for x, y in wire)
        out.append(f'  <path d="{d}" />')

    # 连接点（三条以上线汇于一点时画实心点）。判据是「这个坐标出现了 ≥3 次」
    counts = {}
    for wire in frag["wires"]:
        for p in (wire[0], wire[-1]):
            counts[p] = counts.get(p, 0) + 1
        for p in wire[1:-1]:
            counts[p] = counts.get(p, 0) + 1
    for p, n in counts.items():
        touching = n + sum(1 for q in pins.values()
                           if abs(q[0] - p[0]) < .75 and abs(q[1] - p[1]) < .75)
        if touching >= 3:
            out.append(f'  <circle cx="{p[0]}" cy="{p[1]}" r="3" '
                       f'fill="currentColor" stroke="none" />')

    # 元件。**`data-sym` 必须写出来**：验收脚本要按端子表算引脚坐标，
    # 而画布尺寸不是符号的唯一标识 —— gnd / vcc / header 都是 32x48，
    # resistor / capacitor / opamp 都是 56x48。第一版让验收脚本按尺寸反推是哪个
    # 符号，于是把 vcc 认成了 gnd（端子一个在底一个在顶，差 48），
    # 报出三处「网表对不上」的假红。producer 知道的事情不要让 consumer 去猜。
    for ref, sym, (cx, cy), rot in frag["parts"]:
        out.append(f'  <g transform="{transform(sym, cx, cy, rot)}" '
                   f'data-ref="{ref}" data-sym="{sym}">')
        out += [f"    {p}" for p in SYMS[sym]["parts"]]
        out.append("  </g>")

    # 标注：用 mono，和站上所有编号同一个语气
    for text, (x, y), anchor in frag["labels"]:
        out.append(f'  <text x="{x}" y="{y}" fill="currentColor" stroke="none" '
                   f'font-family="ui-monospace, monospace" font-size="13" '
                   f'text-anchor="{anchor}">{text}</text>')

    out += ["</svg>", ""]
    return "\n".join(out)


def sheet(frags, path: Path):
    cw, ch = BOX[0] + 20, BOX[1] + 46
    cols = 2
    rows = (len(frags) + cols - 1) // cols
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'viewBox="0 0 {cols * cw} {rows * ch}" '
           f'width="{cols * cw}" height="{rows * ch}">',
           '  <rect x="0" y="0" width="100%" height="100%" fill="#0b0b0e" />']
    for i, f in enumerate(frags):
        ox, oy = (i % cols) * cw + 10, (i // cols) * ch + 10
        body = render(f)
        inner = body[body.index(">") + 1:body.rindex("</svg>")]
        out.append(f'  <g transform="translate({ox} {oy})" color="#e9edf4" '
                   f'fill="none" stroke="currentColor" stroke-width="{STROKE}" '
                   f'stroke-linecap="round" stroke-linejoin="round">{inner}</g>')
        out.append(f'  <text x="{ox + BOX[0] / 2}" y="{oy + BOX[1] + 24}" '
                   f'fill="#e2ab63" font-family="sans-serif" font-size="14" '
                   f'text-anchor="middle">{f["title"]}</text>')
    out += ["</svg>", ""]
    path.write_text("\n".join(out), encoding="utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="原理图片段生成")
    ap.add_argument("--sheet", action="store_true", help="另出联系表供人眼复核")
    args = ap.parse_args()

    frags = build_frags()
    OUT.mkdir(parents=True, exist_ok=True)
    keep = {f"{f['name']}.svg" for f in frags}
    for old in OUT.glob("*.svg"):
        if old.name not in keep:
            old.unlink()
            print(f"  删除不再生成的 {old.name}")

    bad = 0
    for f in frags:
        pins = pins_of(f)
        # 生成时先自查一遍：声明的网表和几何算出来的连通性一致吗
        actual = connectivity(pins, f["wires"])
        declared = [set(v) for v in f["nets"].values()]
        # 只比「声明了的那些节点」——未声明的引脚（比如对外的 Vin）允许单独成组
        for d in declared:
            if not any(d <= a for a in actual):
                print(f"  !! {f['name']}: 声明的节点 {sorted(d)} 在几何上没连上")
                bad += 1
        p = OUT / f"{f['name']}.svg"
        p.write_text(render(f), encoding="utf-8")
        print(f"  {f['name']:14} {len(f['parts'])} 元件 · {len(f['wires'])} 段线 · "
              f"{len(f['nets'])} 个节点  {p.stat().st_size} B")

    if args.sheet:
        shots = REPO / ".shots"
        shots.mkdir(exist_ok=True)
        sheet(frags, shots / "schem-sheet.svg")
        print("联系表：.shots/schem-sheet.svg")
    if bad:
        print(f"\n{bad} 处声明与几何不符 —— 先修好再用")
        return 1
    print(f"\n共 {len(frags)} 张片段")
    return 0


if __name__ == "__main__":
    sys.exit(main())
