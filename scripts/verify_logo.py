# -*- coding: utf-8 -*-
"""验证 brand/logo-mark.svg 对原位图的几何保真度（无需浏览器渲染）。

两个方向都要查：
  正向：我画的中心线上每个采样点，是否都落在原图墨迹内？
        （查"画歪了"）
  反向：原图的每个墨迹像素，到我最近的中心线的距离是否 <= 笔画半径？
        （查"漏画了一整段"——这个更致命）

用完即弃。
"""
import math
import re
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
SVG = REPO / "app" / "static" / "brand" / "logo-mark.svg"
PNG = REPO / "app" / "static" / "img" / "logo-mark.png"

im = Image.open(PNG).convert("RGBA")
W, H = im.size
px = im.split()[-1].load()
ink = [[px[x, y] > 128 for x in range(W)] for y in range(H)]

svg = SVG.read_text(encoding="utf-8")

# ---------- 先查 XML 合法性 ----------
# 独立 .svg 走 XML 解析器，无值属性（data-foo 这种）会让整图解析失败、
# 一片空白，three.js 的 SVGLoader 也会读不出东西。这个坑真实踩过，
# 而纯几何校验完全看不出来（正则不在乎 XML 是否合法）。
import xml.etree.ElementTree as ET  # noqa: E402

try:
    ET.fromstring(svg)
    print("XML 合法性：OK")
except ET.ParseError as exc:
    print(f"XML 合法性：FAIL —— {exc}")
    print("  独立 .svg 按 XML 解析，检查是否有无值属性、未闭合标签、未转义的 & < >")
    raise SystemExit(1)

# 去掉注释，避免把注释里的数字当路径
svg_body = re.sub(r"<!--.*?-->", "", svg, flags=re.S)

STROKE = 10.0
HALF = STROKE / 2


def sample_path(d: str, step: float = 0.6):
    """支持 M / L / Q（本文件只用到这三种）。返回中心线采样点。"""
    tokens = re.findall(r"[MLQ]|-?\d+\.?\d*", d)
    pts, cur, i = [], None, 0
    while i < len(tokens):
        cmd = tokens[i]
        i += 1
        if cmd == "M":
            cur = (float(tokens[i]), float(tokens[i + 1]))
            i += 2
            pts.append(cur)
        elif cmd == "L":
            nxt = (float(tokens[i]), float(tokens[i + 1]))
            i += 2
            dist = math.dist(cur, nxt)
            n = max(2, int(dist / step))
            for k in range(1, n + 1):
                t = k / n
                pts.append((cur[0] + (nxt[0] - cur[0]) * t, cur[1] + (nxt[1] - cur[1]) * t))
            cur = nxt
        elif cmd == "Q":
            c = (float(tokens[i]), float(tokens[i + 1]))
            nxt = (float(tokens[i + 2]), float(tokens[i + 3]))
            i += 4
            n = 40
            for k in range(1, n + 1):
                t = k / n
                x = (1 - t) ** 2 * cur[0] + 2 * (1 - t) * t * c[0] + t * t * nxt[0]
                y = (1 - t) ** 2 * cur[1] + 2 * (1 - t) * t * c[1] + t * t * nxt[1]
                pts.append((x, y))
            cur = nxt
    return pts


centers = []
for m in re.finditer(r'd="([^"]+)"', svg_body):
    centers.extend(sample_path(m.group(1)))

circles = []
for m in re.finditer(r'<circle[^>]*cx="([\d.]+)"[^>]*cy="([\d.]+)"[^>]*r="([\d.]+)"', svg_body):
    cx, cy, r = float(m.group(1)), float(m.group(2)), float(m.group(3))
    circles.append((cx, cy, r))
    for k in range(360):
        a = math.radians(k)
        centers.append((cx + r * math.cos(a), cy + r * math.sin(a)))

print(f"解析到 {len(re.findall(chr(100) + '=' + chr(34), svg_body))} 条 path、{len(circles)} 个焊盘环")
print(f"中心线采样点 {len(centers)} 个\n")

# ---------- 正向：采样点是否在墨迹内 ----------
inside = 0
strays = []
for x, y in centers:
    xi, yi = int(round(x)), int(round(y))
    hit = False
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            X, Y = xi + dx, yi + dy
            if 0 <= X < W and 0 <= Y < H and ink[Y][X]:
                hit = True
                break
        if hit:
            break
    if hit:
        inside += 1
    else:
        strays.append((round(x, 1), round(y, 1)))
ratio = inside / len(centers) * 100
print(f"正向：{inside}/{len(centers)} = {ratio:.2f}% 的中心线采样点落在原图墨迹内")
if strays:
    print(f"  偏离原图的采样点 {len(strays)} 个，前 12 个：{strays[:12]}")

# ---------- 反向：原图墨迹是否都被覆盖 ----------
# 网格加速最近点查询
CELL = 8
grid = {}
for x, y in centers:
    grid.setdefault((int(x // CELL), int(y // CELL)), []).append((x, y))


def nearest(x, y):
    gx, gy = int(x // CELL), int(y // CELL)
    best = 1e9
    rad = 1
    while rad < 8:
        found = False
        for i in range(gx - rad, gx + rad + 1):
            for j in range(gy - rad, gy + rad + 1):
                for cx, cy in grid.get((i, j), ()):
                    d = (cx - x) ** 2 + (cy - y) ** 2
                    if d < best:
                        best = d
                        found = True
        if found and best <= (rad * CELL) ** 2:
            break
        rad += 2
    return math.sqrt(best)


dists = []
uncovered = []
for y in range(H):
    for x in range(W):
        if not ink[y][x]:
            continue
        d = nearest(x, y)
        dists.append(d)
        if d > HALF + 3.5:      # 焊盘环笔画 7，半径 3.5，放宽到这个量级
            uncovered.append((x, y, round(d, 1)))

dists.sort()
n = len(dists)
print(f"\n反向：原图墨迹 {n} 像素，到最近中心线的距离分布")
for q in (50, 90, 99, 100):
    print(f"  P{q:<3d} = {dists[min(n - 1, q * n // 100)]:.2f}px")
print(f"  超出容差（>{HALF + 3.5}px）的像素：{len(uncovered)} 个"
      f"（占 {len(uncovered) / n * 100:.2f}%）")
if uncovered:
    # 按区域聚合，看是不是漏了一整段
    buckets = {}
    for x, y, d in uncovered:
        buckets.setdefault((x // 24 * 24, y // 24 * 24), 0)
        buckets[(x // 24 * 24, y // 24 * 24)] += 1
    print("  未覆盖像素的区域分布（24x24 格）：")
    for (bx, by), cnt in sorted(buckets.items(), key=lambda kv: -kv[1])[:10]:
        print(f"    x∈[{bx},{bx + 24}) y∈[{by},{by + 24})  {cnt} 像素")

# ---------- 不变量：焊盘内孔必须是空的 ----------
# 这是真实踩过的 bug：走线画到焊盘圆心，内孔被填掉，焊盘变成实心圆点。
# 环的墨迹只占半径 7.5~14.5，内孔（半径 < 7.5）必须一点墨都没有。
HOLE_R = 7.5
trace_pts = []
for m in re.finditer(r'd="([^"]+)"', svg_body):
    trace_pts.extend(sample_path(m.group(1), step=0.4))

hole_violations = []
for cx, cy, ring_r in circles:
    # 在内孔里撒点，检查有没有落在任何走线的墨迹范围内（笔画半宽 5）
    steps = 26
    for i in range(steps + 1):
        for j in range(steps + 1):
            hx = cx - HOLE_R + 2 * HOLE_R * i / steps
            hy = cy - HOLE_R + 2 * HOLE_R * j / steps
            if math.dist((hx, hy), (cx, cy)) > HOLE_R - 0.5:
                continue
            for tx, ty in trace_pts:
                if math.dist((hx, hy), (tx, ty)) <= HALF:
                    hole_violations.append((round(cx), round(cy), round(hx, 1), round(hy, 1)))
                    break
            else:
                continue
            break
        if hole_violations and hole_violations[-1][0] == round(cx):
            break

print("\n焊盘内孔检查（半径 %.1f 内不允许有走线墨迹）：" % HOLE_R)
if hole_violations:
    for cx, cy, hx, hy in hole_violations:
        print(f"  ! 焊盘 ({cx},{cy}) 的内孔被走线填入，例如孔内点 ({hx},{hy})")
else:
    print(f"  OK  {len(circles)} 个焊盘内孔全部干净")

ok = ratio > 97 and len(uncovered) / n < 0.06 and not hole_violations
print("\n" + ("会标矢量验证通过" if ok else "验证未通过，需要调整坐标"))
raise SystemExit(0 if ok else 1)
