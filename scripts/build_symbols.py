# -*- coding: utf-8 -*-
"""电路符号库生成脚本（改了几何数据就重跑一次）。

产出：`app/static/brand/sym/*.svg` —— 一套**原理图符号**，不是图标。

为什么是生成的，不是手画的
--------------------------
和走线数字（`build_lettering.py`）同一个理由：这些东西有**几何约束**，
手画必然漂移。符号库的约束比图标多一层 ——

  1. 所有符号共用同一个**栅格**（步长 4）与同一个**线宽**（1.7，和
     `includes/icon.html` 那套线性图标同源，两者要看起来是一家人）。
  2. 每个符号的**端子**必须落在栅格上，而且必须记录在数据里 ——
     D4 的原理图片段要把符号连起来，连线得知道往哪连。手画的 SVG 里
     「引线末端在哪」只存在于眼睛里，拼图的时候就会差半个像素。
  3. 引线长度统一（`LEAD`），否则并排放一列时符号本体左右不齐。

**这是电子科技协会的站，符号画错比没有更糟。** 所以：几何写在数据里、
`check_symbols.py` 逐条量、而「符号对不对」这件事脚本判不了，得看图 ——
生成完跑 `--sheet` 出一张联系表，逐个对着教材看。

画法沿用国内教材/IEC：电阻是矩形（不是美式锯齿），电容是两条平行板，
电感是四个半圆弧，二极管是三角加竖线。

跑法：
    python scripts/build_symbols.py            # 生成全部
    python scripts/build_symbols.py --sheet    # 另出一张联系表（人眼复核）
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "app" / "static" / "brand" / "sym"

# 栅格步长。所有端子坐标必须是它的整数倍 —— check_symbols.py 逐个量。
GRID = 4
# 线宽。和 includes/icon.html 的线性图标一致，两套要像一家人。
STROKE = 1.7
# 引线长度（从画布边缘到本体）。统一才能并排对齐。
LEAD = 8


def sym(name, label, box, terminals, parts, extra=""):
    return {"name": name, "label": label, "box": box,
            "terminals": terminals, "parts": parts, "extra": extra}


def arrowhead(x, y, dx, dy, size=5.5):
    """实心箭头。三极管的发射极、MOSFET 的衬底都用它。

    **用实心三角而不是两笔勾**：这套符号在页面上只有 30px 高，两笔勾出来的
    箭头在那个尺寸下糊成一个点，而「箭头朝哪」正是 NPN/PNP、N 沟道/P 沟道
    的唯一区别 —— 看不清等于画错。所以这一处**刻意**跳出 `fill="none"`
    的家族约定，单独给 `fill="currentColor"`。
    """
    import math

    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    px, py = -uy, ux                      # 垂线
    bx, by = x - ux * size, y - uy * size
    half = size * 0.42
    return (f'<path d="M{x:.1f} {y:.1f}L{bx + px * half:.1f} {by + py * half:.1f}'
            f'L{bx - px * half:.1f} {by - py * half:.1f}Z" '
            f'fill="currentColor" stroke="none" />')


def build_data():
    """几何数据。坐标单位是 user unit，端子必须落在 GRID 上。

    **所有符号的画布高度统一是 48**，宽度可以不同。这一条是效果决定的，
    不是整齐癖：符号在页面上按**固定高度**渲染（`height: 30px`），
    高度不统一就等于缩放比例不统一，于是同一套符号的**线宽看起来不一样粗** ——
    电阻和三极管放在一列里像两套图。第一版两端元件给 32、三极管给 48，
    出来就是这个毛病。

    两端元件：56x48，端子在 (0,24) 与 (56,24)。中线以上留 24 个单位，
    发光二极管的两道箭头和电解电容的极性号都放得下 —— 第一版给 32 高，
    LED 的箭头没地方去，挤成了一个钩子。
    """
    S = []
    CY = 24          # 两端元件的中线
    W2 = 56          # 两端元件画布宽
    H = 48           # 全部符号统一画布高
    body_l, body_r = LEAD + 6, W2 - LEAD - 6      # 本体左右边界 = 14 / 42

    cx = W2 / 2      # 28

    # ---- 电阻：矩形。国内教材与 IEC 都是矩形，不是美式锯齿 ----
    S.append(sym(
        "resistor", "电阻", (W2, H), [(0, CY), (W2, CY)],
        [f'<path d="M0 {CY}h{body_l}M{body_r} {CY}h{LEAD + 6}" />',
         f'<rect x="{body_l}" y="{CY - 7}" width="{body_r - body_l}" height="14" '
         f'rx="1.5" />']))

    # ---- 电容（无极性）：两条平行板 ----
    S.append(sym(
        "capacitor", "电容", (W2, H), [(0, CY), (W2, CY)],
        [f'<path d="M0 {CY}h{cx - 3}M{cx + 3} {CY}h{cx - 3}" />',
         f'<path d="M{cx - 3} {CY - 11}v22M{cx + 3} {CY - 11}v22" />']))

    # ---- 电解电容：一直板 + 一弧板。弧要**明显**是弧 ----
    # 第一版半径给 13、弦长 22，弧高只有 2.4 个单位，30px 下看着和直线一样。
    # 半径压到 15 但走短弧（弦 22、弧高约 4.5）才看得出来。
    S.append(sym(
        "capacitor-pol", "电解电容", (W2, H), [(0, CY), (W2, CY)],
        [f'<path d="M0 {CY}h{cx - 3}M{cx + 7} {CY}h{cx - 7}" />',
         f'<path d="M{cx - 3} {CY - 11}v22" />',
         # 弧板：向右凸（背对直板），弦长 22、弧高约 4.5
         f'<path d="M{cx + 3} {CY - 11}a15 15 0 0 1 0 22" />',
         # 正极记号：紧贴直板上方（直板那一侧是正极）
         f'<path d="M{cx - 13} {CY - 15}h6M{cx - 10} {CY - 18}v6" />']))

    # ---- 电感：四个半圆弧，弧朝上 ----
    r = 5
    arcs = "".join(f"a{r} {r} 0 0 1 {2 * r} 0" for _ in range(4))
    S.append(sym(
        "inductor", "电感", (W2, H), [(0, CY), (W2, CY)],
        [f'<path d="M0 {CY}h{body_l - 4}M{body_r + 4} {CY}h{LEAD + 2}" />',
         f'<path d="M{body_l - 4} {CY}{arcs}" />']))

    # 二极管家族共用的三角（尖指向阴极 = 正向电流方向）与阴极竖线
    tri = f'M{cx - 8} {CY - 9}L{cx + 5} {CY}L{cx - 8} {CY + 9}Z'
    cath = f'M{cx + 5} {CY - 9}v18'
    leads = f'M0 {CY}h{cx - 8}M{cx + 5} {CY}h{cx - 5}'

    S.append(sym("diode", "二极管", (W2, H), [(0, CY), (W2, CY)],
                 [f'<path d="{leads}" />', f'<path d="{tri}" />',
                  f'<path d="{cath}" />']))

    # ---- 发光二极管：二极管 + 两道朝外的平行箭头 ----
    # 第一版把箭头挤在 32 高的画布里，只剩 7 个单位，出来是个钩子。
    # 现在画布 48 高、中线在 24，上方有 15 个单位可用。
    led = [f'<path d="{leads}" />', f'<path d="{tri}" />', f'<path d="{cath}" />']
    for i, sx in enumerate((cx - 6, cx + 1)):
        sy = CY - 12
        ex, ey = sx + 7, sy - 7          # 45° 朝右上
        led.append(f'<path d="M{sx} {sy}L{ex} {ey}" />')
        led.append(arrowhead(ex, ey, 1, -1, 4.6))
    S.append(sym("led", "发光二极管", (W2, H), [(0, CY), (W2, CY)], led))

    # ---- 稳压（齐纳）二极管：阴极线两端各折一小段，成一个「旗」 ----
    # 第一版写成一条斜着折的线，读不出是齐纳。正确画法是竖线不动，
    # 上端向左折、下端向右折（或反之），两折同长。
    S.append(sym(
        "zener", "稳压二极管", (W2, H), [(0, CY), (W2, CY)],
        [f'<path d="{leads}" />', f'<path d="{tri}" />',
         f'<path d="M{cx} {CY - 9}h5v18h5" />']))

    # ---- NPN 三极管 ----
    # 端子：基极在左、集电极在上、发射极在下。发射极箭头**朝外**（NPN）。
    bx = 18                     # 基线 x
    S.append(sym(
        "bjt-npn", "NPN 三极管", (48, H), [(0, 24), (36, 0), (36, 48)],
        [f'<circle cx="24" cy="24" r="18" />',
         f'<path d="M0 24h{bx}" />',
         f'<path d="M{bx} 14v20" />',                 # 基线
         f'<path d="M{bx} 19L36 10V0" />',            # 集电极
         f'<path d="M{bx} 29L36 38V48" />',           # 发射极
         arrowhead(30, 34.75, 18, 10.125)]))         # 发射极箭头，朝外

    # ---- N 沟道 MOSFET（增强型） ----
    # 三段沟道之间**必须留看得出的缝**：第一版三段首尾几乎相接（13-20 / 20.5-27.5
    # / 28-35），渲染出来是一条连续竖线，读成结型而不是增强型。
    S.append(sym(
        "mosfet-n", "N 沟道 MOSFET", (48, H), [(0, 24), (36, 0), (36, 48)],
        [f'<circle cx="24" cy="24" r="18" />',
         f'<path d="M0 24h12" />',
         f'<path d="M12 15v18" />',                   # 栅极板
         f'<path d="M17 15v6M17 21v6M17 27v6" />',    # 沟道三段（缝 3 个单位）
         f'<path d="M17 18L36 18V0" />',              # 漏极
         f'<path d="M17 30L36 30V48" />',             # 源极
         f'<path d="M17 24h11v6" />',                 # 衬底：并到源极
         arrowhead(19, 24, -1, 0, 5.0)]))            # 箭头指向沟道（N 沟道朝左）

    # ---- 运放：三角 + ± 两输入。同 includes/icon.html 的 opamp 一脉 ----
    # 输入端子取 12 / 36 而不是 14 / 34：端子必须落在栅格（步长 4）上，
    # 否则 D4 拼原理图时连线对不齐。这一条 check_symbols.py 逐个量。
    # ± 记号给 8 个单位而不是 5：运放的两个输入**哪个是反相**是读懂反馈电路的
    # 全部信息（跟随器把输出接回 − 才成立，接回 + 就是正反馈、会自锁）。
    # 5 个单位在页面上的原理图里只有 7px，看不出来等于没画。
    S.append(sym(
        "opamp", "运算放大器", (56, H), [(0, 12), (0, 36), (56, 24)],
        [f'<path d="M0 12h14M0 36h14M42 24h14" />',
         f'<path d="M14 4v40l28-20Z" />',
         f'<path d="M18 12h8" />',                       # − 号（上输入）
         f'<path d="M18 36h8M22 32v8" />']))             # + 号（下输入）

    # ---- 晶振：两板夹一个矩形 ----
    S.append(sym(
        "crystal", "晶振", (W2, H), [(0, CY), (W2, CY)],
        [f'<path d="M0 {CY}h{cx - 8}M{cx + 8} {CY}h{cx - 8}" />',
         f'<path d="M{cx - 8} {CY - 10}v20M{cx + 8} {CY - 10}v20" />',
         f'<rect x="{cx - 4}" y="{CY - 12}" width="8" height="24" rx="1" />']))

    # ---- 接地 ----
    S.append(sym(
        "gnd", "接地", (32, H), [(16, 0)],
        [f'<path d="M16 0v24" />',
         f'<path d="M5 24h22M9 30h14M13 36h6" />']))

    # ---- 电源（VCC 箭头） ----
    S.append(sym(
        "vcc", "电源", (32, H), [(16, 48)],
        [f'<path d="M16 48V12" />',
         f'<path d="M9 19l7-7 7 7" />']))

    # ---- 开关（单刀单掷，常开） ----
    S.append(sym(
        "switch", "开关", (W2, H), [(0, CY), (W2, CY)],
        [f'<path d="M0 {CY}h{body_l}M{body_r} {CY}h{LEAD + 6}" />',
         f'<circle cx="{body_l}" cy="{CY}" r="2" />',
         f'<circle cx="{body_r}" cy="{CY}" r="2" />',
         f'<path d="M{body_l + 1.8} {CY - 1.2}l{body_r - body_l - 4} -9" />']))

    # ---- 排针 / 接插件（两位） ----
    S.append(sym(
        "header", "排针", (32, H), [(32, 16), (32, 32)],
        [f'<rect x="4" y="8" width="12" height="32" rx="1.5" />',
         f'<path d="M16 16h16M16 32h16" />',
         f'<circle cx="10" cy="16" r="2" />',
         f'<circle cx="10" cy="32" r="2" />']))

    return S


HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        'fill="none" stroke="currentColor" stroke-width="{sw}" '
        'stroke-linecap="round" stroke-linejoin="round">')


def render(s) -> str:
    """一个符号一份 SVG。

    **每个属性都必须带值。** 这是会标那次的教训：独立 `.svg` 走 XML 解析，
    无值属性（写成 `fill` 而不是 `fill="none"`）会让整张图解析失败，
    而页面只是少一块东西、不报错。`verify_logo.py` 与 `check_symbols.py`
    都钉着这一条。

    端子坐标写进 `data-terminals`：这不是装饰，是给 D4 的原理图拼装用的 ——
    连线要知道往哪连。写在文件里而不是另建一份清单，是为了不出现「两份会漂」。
    """
    w, h = s["box"]
    terms = " ".join(f"{x},{y}" for x, y in s["terminals"])
    lines = [HEAD.format(w=w, h=h, sw=STROKE),
             f'  <title>{s["label"]}的原理图符号</title>',
             f'  <g data-terminals="{terms}" data-grid="{GRID}">']
    lines += [f"    {p}" for p in s["parts"]]
    if s["extra"]:
        lines.append(f"    {s['extra']}")
    lines += ["  </g>", "</svg>", ""]
    return "\n".join(lines)


def sheet(symbols, path: Path):
    """联系表：一页里把全部符号排开，给人眼逐个对着教材看。"""
    cols, cw, ch = 4, 150, 120
    rows = (len(symbols) + cols - 1) // cols
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" '
           f'viewBox="0 0 {cols * cw} {rows * ch}" '
           f'width="{cols * cw}" height="{rows * ch}">',
           '  <rect x="0" y="0" width="100%" height="100%" fill="#0b0b0e" />']
    for i, s in enumerate(symbols):
        cx, cy = (i % cols) * cw, (i // cols) * ch
        w, h = s["box"]
        k = min(90 / w, 56 / h)
        ox, oy = cx + (cw - w * k) / 2, cy + 26
        out.append(f'  <g transform="translate({ox:.1f} {oy:.1f}) scale({k:.3f})" '
                   f'fill="none" stroke="#e9edf4" stroke-width="{STROKE}" '
                   f'stroke-linecap="round" stroke-linejoin="round">')
        out += [f"    {p}" for p in s["parts"]]
        # 端子画成小圆点，肉眼确认引线末端和端子重合
        for x, y in s["terminals"]:
            out.append(f'    <circle cx="{x}" cy="{y}" r="2.4" fill="#e2ab63" '
                       f'stroke="none" />')
        out.append("  </g>")
        out.append(f'  <text x="{cx + cw / 2}" y="{cy + ch - 18}" fill="#97a1b3" '
                   f'font-family="sans-serif" font-size="13" '
                   f'text-anchor="middle">{s["label"]}</text>')
        out.append(f'  <text x="{cx + cw / 2}" y="{cy + ch - 4}" fill="#767f8f" '
                   f'font-family="monospace" font-size="10" '
                   f'text-anchor="middle">{s["name"]}</text>')
    out += ["</svg>", ""]
    path.write_text("\n".join(out), encoding="utf-8")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="电路符号库生成")
    ap.add_argument("--sheet", action="store_true",
                    help="另出一张联系表 .shots/sym-sheet.svg（人眼复核画法）")
    args = ap.parse_args()

    symbols = build_data()
    OUT.mkdir(parents=True, exist_ok=True)
    # 先清掉不再生成的旧符号：改名之后留着一份孤儿 SVG，模板引用它照常渲染，
    # 于是「改名」这件事永远发现不了。
    keep = {f"{s['name']}.svg" for s in symbols}
    for old in OUT.glob("*.svg"):
        if old.name not in keep:
            old.unlink()
            print(f"  删除不再生成的 {old.name}")

    total = 0
    for s in symbols:
        p = OUT / f"{s['name']}.svg"
        p.write_text(render(s), encoding="utf-8")
        total += p.stat().st_size
        print(f"  {s['name']:16} {s['box'][0]}x{s['box'][1]}  "
              f"{len(s['terminals'])} 端子  {p.stat().st_size} B")
    print(f"\n共 {len(symbols)} 个符号，合计 {total / 1024:.1f} KB")

    if args.sheet:
        shots = REPO / ".shots"
        shots.mkdir(exist_ok=True)
        sheet(symbols, shots / "sym-sheet.svg")
        print("联系表：.shots/sym-sheet.svg（端子画成铜色圆点）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
