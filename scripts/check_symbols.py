# -*- coding: utf-8 -*-
"""电路符号库验收：把 `build_symbols.py` 出来的 SVG 逐个量一遍。

判据都是「静默故障」那一类 —— 错了页面照常渲染、控制台干净：

1. **每个属性都要带值。** 独立 `.svg` 走 XML 解析，`fill` 写成无值属性会让
   整张图解析失败，而页面只是少一块东西。会标那次踩过（见 verify_logo.py）。
2. **画布高度必须全都是 48。** 符号在页面上按固定高度渲染，高度不统一
   = 缩放比例不统一 = **同一套符号的线宽看起来不一样粗**。这个错在联系表上
   要两个符号挨着才看得出来，单看一个永远发现不了。
3. **线宽必须是 1.7**，和 `includes/icon.html` 那套线性图标同源。
4. **端子必须落在栅格上**（步长 4）。D4 要把这些符号连成原理图，
   端子不在栅格上，连线就会差半个像素 —— 而那时候图已经画完了。
5. **每个端子都必须真的有一条引线画到那里。** 这是最重要的一条：
   `data-terminals` 是给拼图用的坐标表，如果它和实际画出来的引线末端不一致，
   拼出来的原理图就是「线连到空气里」—— 而单看符号本身完全正常。

跑法：
    python scripts/check_symbols.py
    python scripts/check_symbols.py --dump   # 打印每个符号的锚点，排查用
"""
import argparse
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SYM = REPO / "app" / "static" / "brand" / "sym"

GRID = 4
STROKE = "1.7"
BOX_H = 48
ICON_TEMPLATE = REPO / "app" / "templates" / "includes" / "icon.html"

failures: list[str] = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def path_anchors(d: str):
    """把 path 的 `d` 走一遍，返回所有锚点（每段的起止点）。

    只需要覆盖这套符号实际用到的命令：M/L/H/V/A/Z 及其小写。
    **不求精确弧线**，只要弧的两个端点 —— 我们要回答的问题是
    「有没有一条线画到端子那里」，端点就够了。

    刻意不引第三方 svg 库：多一个依赖，而这里只需要几十行。
    """
    pts = []
    i = 0
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    tokens = re.findall(r"[MmLlHhVvAaZzCcSsQqTt]|[-+]?\d*\.?\d+", d)
    while i < len(tokens):
        cmd = tokens[i]
        i += 1
        if cmd in "Zz":
            cur = start
            pts.append(cur)
            continue
        # 同一个命令可以跟多组参数
        while i < len(tokens) and not tokens[i].isalpha():
            if cmd in "Mm":
                x, y = float(tokens[i]), float(tokens[i + 1])
                i += 2
                cur = (x, y) if cmd == "M" else (cur[0] + x, cur[1] + y)
                start = cur
            elif cmd in "Ll":
                x, y = float(tokens[i]), float(tokens[i + 1])
                i += 2
                cur = (x, y) if cmd == "L" else (cur[0] + x, cur[1] + y)
            elif cmd in "Hh":
                x = float(tokens[i])
                i += 1
                cur = (x, cur[1]) if cmd == "H" else (cur[0] + x, cur[1])
            elif cmd in "Vv":
                y = float(tokens[i])
                i += 1
                cur = (cur[0], y) if cmd == "V" else (cur[0], cur[1] + y)
            elif cmd in "Aa":
                # rx ry rot large sweep x y
                x, y = float(tokens[i + 5]), float(tokens[i + 6])
                i += 7
                cur = (x, y) if cmd == "A" else (cur[0] + x, cur[1] + y)
            else:
                # 这套符号里不该出现三次曲线；出现了就该有人来加分支
                raise ValueError(f"path 里有未支持的命令 {cmd!r}")
            pts.append(cur)
    return pts


def shape_anchors(el) -> list:
    """rect / circle 的关键点。端子不会落在它们身上，但一起收着便于排查。"""
    t = el.tag.split("}")[-1]
    g = lambda k, d=0.0: float(el.get(k, d))  # noqa: E731
    if t == "rect":
        x, y, w, h = g("x"), g("y"), g("width"), g("height")
        return [(x, y), (x + w, y), (x, y + h), (x + w, y + h),
                (x, y + h / 2), (x + w, y + h / 2)]
    if t == "circle":
        cx, cy, r = g("cx"), g("cy"), g("r")
        return [(cx - r, cy), (cx + r, cy), (cx, cy - r), (cx, cy + r)]
    return []


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="电路符号库验收")
    ap.add_argument("--dump", action="store_true", help="打印每个符号的锚点")
    args = ap.parse_args()

    files = sorted(SYM.glob("*.svg"))
    print(f"符号库 {SYM.relative_to(REPO)}  共 {len(files)} 个")
    check(len(files) >= 12, "符号数量够一套（≥12，不然这份检查等于空跑）",
          f"{len(files)} 个")
    if not files:
        print("\n一个符号都没有，先跑 python scripts/build_symbols.py")
        return 1

    boxes, strokes = set(), set()
    for p in files:
        name = p.stem
        try:
            root = ET.fromstring(p.read_text(encoding="utf-8"))
        except ET.ParseError as e:
            check(False, f"{name} XML 可解析（无值属性会让整图解析失败）", str(e))
            continue

        vb = (root.get("viewBox") or "").split()
        ok_vb = len(vb) == 4 and vb[0] == "0" and vb[1] == "0"
        if not ok_vb:
            check(False, f"{name} viewBox 形如 '0 0 w h'", root.get("viewBox") or "无")
            continue
        w, h = float(vb[2]), float(vb[3])
        boxes.add(h)
        strokes.add(root.get("stroke-width"))

        g = root.find("{http://www.w3.org/2000/svg}g")
        if g is None:
            check(False, f"{name} 有 <g data-terminals>（拼原理图要读它）")
            continue
        raw = g.get("data-terminals") or ""
        terms = [tuple(float(v) for v in t.split(",")) for t in raw.split() if t]
        check(bool(terms), f"{name} 声明了端子", raw or "无")

        # 端子在栅格上
        off = [t for t in terms if any(abs(v % GRID) > 1e-6 for v in t)]
        check(not off, f"{name} 端子都落在栅格上（步长 {GRID}）",
              f"越格 {off}" if off else f"{len(terms)} 个")

        # 端子在画布边界上（引线要从边缘进来，否则拼图时符号之间会有缝）
        edge = [t for t in terms
                if not (abs(t[0]) < 1e-6 or abs(t[0] - w) < 1e-6
                        or abs(t[1]) < 1e-6 or abs(t[1] - h) < 1e-6)]
        check(not edge, f"{name} 端子都在画布边缘上",
              f"不在边上 {edge}" if edge else "")

        # ---- 关键：每个端子都要有一条实际画出来的线到达 ----
        anchors = []
        for el in g.iter():
            tag = el.tag.split("}")[-1]
            if tag == "path" and el.get("d"):
                try:
                    anchors += path_anchors(el.get("d"))
                except ValueError as e:
                    check(False, f"{name} path 可解析", str(e))
            else:
                anchors += shape_anchors(el)
        if args.dump:
            print(f"       锚点 {[(round(x, 1), round(y, 1)) for x, y in anchors]}")
        missing = [t for t in terms
                   if not any(math.dist(t, a) < 0.75 for a in anchors)]
        check(not missing,
              f"{name} **每个端子都有引线画到那里**（不然拼出来是线连到空气里）",
              f"悬空 {missing}" if missing else f"{len(terms)} 个都接上了")

    print("\n整套的一致性（错了要两个符号挨着才看得出来）")
    check(boxes == {BOX_H},
          f"**画布高度全是 {BOX_H}**（高度不一致 = 线宽看起来不一样粗）",
          f"实际 {sorted(boxes)}")
    check(strokes == {STROKE}, f"线宽全是 {STROKE}（和线性图标同源）",
          f"实际 {sorted(x or '无' for x in strokes)}")

    # 和图标集的家族一致性：icon.html 那套也得是 1.7，改一边忘一边就分家了
    if ICON_TEMPLATE.exists():
        t = ICON_TEMPLATE.read_text(encoding="utf-8")
        m = re.search(r'stroke-width="([\d.]+)"', t)
        check(bool(m) and m.group(1) == STROKE,
              "includes/icon.html 的线宽也是这个值（两套要像一家人）",
              m.group(1) if m else "没找到")

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("电路符号库验收全部通过")
    print("（画法对不对脚本判不了 —— 跑 build_symbols.py --sheet 出联系表对着教材看）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
