# -*- coding: utf-8 -*-
"""原理图片段验收：从**画出来的几何**重新算一遍连通性，和声明的网表比对。

为什么这份检查是这一步的核心
----------------------------
「电路图接错了」是最典型的静默故障：SVG 照常渲染、页面照常好看、
控制台干净 —— 而图是错的，而新手会照着它接。肉眼也很难发现，
因为两条线差两个像素没接上，看起来就是接上的。

所以判据不是「文件在不在」，而是：

  把每个元件按它的 `transform` 放好、算出每个引脚的绝对坐标，
  再把线段端点按坐标合并，得出**实际网表**；
  然后和 SVG 里 `data-nets` 声明的那份比。不一致就判红。

这等于用几何证明了「声明的电路 == 画出来的电路」。生成脚本里也有一份同样的
自查（改数据的时候当场就能发现），这里再从**产物**上验一遍 ——
产物才是访客真正看到的东西。

另外拦两条低级但致命的：
  · 有没有引脚**悬空**（不在任何声明的节点里，也没有对外标注）
  · 线段端点有没有落在半个栅格上（原理图的线必须走整格，否则接点对不齐）

跑法：
    python scripts/check_schematics.py
    python scripts/check_schematics.py --dump   # 打印实际网表，排查用
"""
import argparse
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
SCHEM = REPO / "app" / "static" / "brand" / "schem"

from build_symbols import build_data  # noqa: E402

SYMS = {s["name"]: s for s in build_data()}
NS = "{http://www.w3.org/2000/svg}"
GRID = 8
failures: list[str] = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def parse_transform(t: str):
    """只需要认 `translate(a b) rotate(r) translate(c d)` 这一种形式 ——
    生成脚本就只产出这一种。出现别的形式说明有人手改了产物，那就该报错。"""
    nums = re.findall(r"translate\(([-\d.]+) ([-\d.]+)\)|rotate\(([-\d.]+)\)", t)
    if len(nums) != 3:
        raise ValueError(f"看不懂的 transform: {t!r}")
    (ax, ay, _), (_, _, rot), (bx, by, _) = nums
    return float(ax), float(ay), float(rot), float(bx), float(by)


def wire_points(d: str):
    """连线只用 M/L 绝对坐标（生成脚本如此），取出全部折点。"""
    vals = re.findall(r"[-\d.]+", d)
    return [(float(vals[i]), float(vals[i + 1])) for i in range(0, len(vals), 2)]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="原理图片段验收")
    ap.add_argument("--dump", action="store_true", help="打印实际算出来的网表")
    args = ap.parse_args()

    files = sorted(SCHEM.glob("*.svg"))
    print(f"原理图片段 {SCHEM.relative_to(REPO)}  共 {len(files)} 张")
    check(len(files) >= 3, "片段数量够（≥3，不然这份检查等于空跑）", f"{len(files)} 张")
    if not files:
        print("\n先跑 python scripts/build_schematics.py")
        return 1

    boxes = set()
    for p in files:
        name = p.stem
        try:
            root = ET.fromstring(p.read_text(encoding="utf-8"))
        except ET.ParseError as e:
            check(False, f"{name} XML 可解析", str(e))
            continue
        vb = (root.get("viewBox") or "").split()
        boxes.add((vb[2], vb[3]) if len(vb) == 4 else None)

        declared_raw = root.get("data-nets") or ""
        declared = {}
        for chunk in declared_raw.split(";"):
            if "=" in chunk:
                k, v = chunk.split("=", 1)
                declared[k] = set(v.split(","))
        check(bool(declared), f"{name} 声明了网表（data-nets）", declared_raw or "无")

        # ---- 从几何算引脚坐标 ----
        pins = {}
        for g in root.findall(f"{NS}g"):
            ref = g.get("data-ref")
            if not ref:
                continue
            try:
                ax, ay, rot, bx, by = parse_transform(g.get("transform") or "")
            except ValueError as e:
                check(False, f"{name} {ref} 的 transform 可解析", str(e))
                continue
            # 用 `data-sym` 而**不是按画布尺寸反推**是哪个符号。
            # 第一版按尺寸猜，结果 gnd / vcc / header 都是 32x48、
            # resistor / capacitor / opamp 都是 56x48 —— vcc 被认成 gnd
            # （端子一个在底一个在顶，差 48），报出三处假红。
            sym = g.get("data-sym")
            if sym not in SYMS:
                check(False, f"{name} {ref} 写了 data-sym 且认得出来", sym or "无")
                continue
            w, h = SYMS[sym]["box"]
            check(abs(-bx * 2 - w) < 1e-6 and abs(-by * 2 - h) < 1e-6,
                  f"{name} {ref} 的 transform 和 {sym} 的画布对得上",
                  f"{-bx * 2}x{-by * 2} vs {w}x{h}")
            a = math.radians(rot)
            ca, sa = round(math.cos(a)), round(math.sin(a))
            for i, (tx, ty) in enumerate(SYMS[sym]["terminals"], start=1):
                lx, ly = tx - w / 2, ty - h / 2
                pins[f"{ref}.{i}"] = (ax + lx * ca - ly * sa, ay + lx * sa + ly * ca)

        # ---- 线段端点必须走整格 ----
        offgrid = []
        wires = []
        for el in root.findall(f"{NS}path"):
            pts = wire_points(el.get("d") or "")
            wires.append(pts)
            offgrid += [q for q in pts if any(abs(v % (GRID / 2)) > 1e-6 for v in q)]
        check(not offgrid, f"{name} 线的折点都走整格（半格 {GRID // 2}）",
              f"越格 {offgrid[:3]}" if offgrid else f"{len(wires)} 段")

        # ---- 合并求实际网表 ----
        parent: dict = {}

        def find(a):
            while parent.setdefault(a, a) != a:
                a = parent[a]
            return a

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        def key(q):
            return (round(q[0] / 0.75), round(q[1] / 0.75))

        for pts in wires:
            for a, b in zip(pts, pts[1:]):
                union(key(a), key(b))
        for q in pins.values():
            find(key(q))
        groups: dict = {}
        for n, q in pins.items():
            groups.setdefault(find(key(q)), set()).add(n)
        actual = list(groups.values())
        if args.dump:
            print(f"       实际网表 {[sorted(g) for g in actual]}")

        # 声明的每个节点，必须整体落在实际的某一个节点里
        wrong = [k for k, v in declared.items()
                 if not any(v <= a for a in actual)]
        check(not wrong,
              f"{name} **声明的网表和画出来的几何一致**（接错的图比没有图更糟）",
              f"对不上的节点：{wrong}" if wrong else f"{len(declared)} 个节点")

        # 反向：实际连在一起的引脚，不能有声明里没提到的额外连接
        #（多连一根线同样是画错，而它不会让上面那条红）
        named = set().union(*declared.values()) if declared else set()
        extra = []
        for a in actual:
            if len(a) < 2:
                continue
            if not any(a <= v for v in declared.values()):
                extra.append(sorted(a))
        check(not extra, f"{name} 没有多连出来的节点（反向也要对得上）",
              f"多出来：{extra}" if extra else "")

        # 悬空引脚：既不在任何声明节点里，也不是对外接口
        dangling = sorted(set(pins) - named)
        check(not dangling, f"{name} 没有悬空引脚", f"悬空 {dangling}" if dangling else "")

    print("\n整套的一致性")
    check(len(boxes) == 1, "画布尺寸全都一样（不一致 = 线宽看起来不一样粗）",
          f"实际 {sorted(str(b) for b in boxes)}")

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("原理图片段验收全部通过")
    print("（画得对不对、好不好读还是要看图：build_schematics.py --sheet）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
