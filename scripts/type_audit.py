# -*- coding: utf-8 -*-
"""排版令牌审计：清点字号/行高/字重/字距，并守住「阶梯不许再被稀释」。

为什么需要它：改版上线后数出来 272 处 `font-size` 声明用了 **51 种取值**，
其中 13 / 13.5 / 14 / 14.5 / 15 / 15.5px 是六个取值在干同一件事 —— 肉眼分不出，
却让版面失去「这两块地位不同」的能力。行高 67 处 20 种同理。

这不是「哪个值更好」的问题，是**没做决定**：每次写新组件时凭手感填一个数，
一年下来就成了 51 种。所以收敛之后必须有东西挡着，否则下一个组件照旧。

两种模式：

    python scripts/type_audit.py --census          # 清点：取值 → 次数 → 用在哪
    python scripts/type_audit.py                   # 检查：字面值不许再出现

检查模式的判据：`font-size` / `line-height` 的值必须是令牌引用（`var(--fs-*)`
/ `var(--lh-*)`），令牌本身只在 `tokens.css` 的 `:root` 里定义。例外必须写进
下面的 ALLOW 表并注明理由 —— 「注明理由」是这份清单唯一的价值所在，
不写理由的例外等于没有约束。
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from css_audit import parse_file  # noqa: E402

# 层叠顺序，也是清点顺序
CSS_FILES = [
    "app/static/css/tokens.css",
    "app/static/css/core.css",
    "app/static/css/home.css",
    "app/static/css/dashboard.css",
]

PROPS = ["font-size", "line-height", "font-weight", "letter-spacing", "font-family", "font"]

# `font:` 简写里也藏着字号和行高：`font: 700 11px/1 var(--font-mono)`。
# 全站有 28 处这样写（几乎都是 mono 小标签）。**逐属性扫是扫不到的** ——
# 这份检查第一版就是这么漏掉 28 处的：它报「font-size 315 处全部走令牌」，
# 而那 28 处压根没被当成 font-size 看。
SIZE_LITERAL = re.compile(r"(?<![\w-])\d[\d.]*px")

# 允许写字面值的地方。键是 (属性, 选择器)，值是理由。
# 理由要写「为什么这里不能用令牌」，不是「这里就是这样」。
ALLOW: dict[tuple[str, str], str] = {
    # 代码片段要跟着它所在的正文按比例缩，不是独立一档 —— 长文正文哪天换档，
    # 行内代码必须跟着走，写成固定档就会在某些段落里比正文还大。
    ("font-size", ".md-body code"): "跟随所在正文按比例缩（em）",
    # 脚注角标同理，而且它更严格：`sup` 出现在正文段里也出现在小标题里，
    # 上标本来就是「比周围的字小一号」这个相对关系，固定档会让它在小标题里比标题还大。
    ("font-size", ".md-body sup"): "上标是相对周围文字的比例关系（em）",
    # 圆形角标：line-height 要和固定的 width/height 对齐才能让数字居中，
    # 用倍数的话字号一变就偏心。这是「几何」不是「排版」。
    ("line-height", ".nav-bell-badge"): "撑起圆形角标的固定高度，必须是 px",
    # 窄屏钉住分镜里的标题：7.2vw 是照着 720–1024px 这一段调的，要在那一段就吃满
    # 宽度。换成通用斜坡（3.8vw）会让它在 700px 处从 40px 掉到 26px。
    ("font-size",
     "html.motion-ready.has-webgl:not(.motion-reduced) .nf-forge-copy .nf-display"):
        "窄屏钉住分镜专用斜坡，vw 系数按 720–1024 段校准",
}


def collect() -> dict:
    """按属性收集：值 -> [(文件, 上下文, 选择器)]。"""
    found = {p: defaultdict(list) for p in PROPS}
    for rel in CSS_FILES:
        decls, _ = parse_file(str(REPO / rel))
        for (ctx, sel, prop), val in decls.items():
            if prop in found:
                found[prop][val].append((Path(rel).name, ctx, sel))
    return found


def census() -> int:
    found = collect()
    for prop in PROPS:
        buckets = found[prop]
        total = sum(len(v) for v in buckets.values())
        print(f"\n{'=' * 72}\n{prop}：{total} 处声明 / {len(buckets)} 种取值\n{'=' * 72}")
        # 能排序的按数值排，排不了的（clamp/var）按次数
        def sort_key(item):
            val, uses = item
            m = re.fullmatch(r"([\d.]+)(px|rem|em|%)?", val)
            return (0, float(m.group(1))) if m else (1, -len(uses))

        for val, uses in sorted(buckets.items(), key=sort_key):
            print(f"\n  {val}   × {len(uses)}")
            for name, ctx, sel in uses:
                where = f"{name}"
                if ctx:
                    where += f" [{ctx}]"
                print(f"      {where}  {sel}")
    return 0


def summary() -> int:
    found = collect()
    for prop in PROPS:
        buckets = found[prop]
        total = sum(len(v) for v in buckets.values())
        print(f"{prop:<16} {total:>4} 处 / {len(buckets):>3} 种")
        def sort_key(item):
            val, uses = item
            m = re.fullmatch(r"([\d.]+)(px|rem|em|%)?", val)
            return (0, float(m.group(1))) if m else (1, -len(uses))
        for val, uses in sorted(buckets.items(), key=sort_key):
            flag = "" if val.startswith("var(") else "  ←字面值"
            print(f"    {val:<46} × {len(uses):<3}{flag}")
        print()
    return 0


def check() -> int:
    found = collect()
    failures = []
    for val, uses in found["font"].items():
        if not SIZE_LITERAL.search(val):
            continue
        for name, ctx, sel in uses:
            failures.append(("font", val, name, ctx, sel))
    for prop in ("font-size", "line-height"):
        for val, uses in found[prop].items():
            if val.startswith("var("):
                continue
            for name, ctx, sel in uses:
                if (prop, sel) in ALLOW:
                    continue
                failures.append((prop, val, name, ctx, sel))

    if failures:
        print(f"{len(failures)} 处字面值绕开了排版令牌：")
        for prop, val, name, ctx, sel in sorted(failures):
            where = f"{name}" + (f" [{ctx}]" if ctx else "")
            print(f"  - {where}  {sel} {{ {prop}: {val} }}")
        print("\n改成 var(--fs-*) / var(--lh-*)；确有理由的写进 type_audit.py 的 ALLOW 并注明理由。")
        return 1

    # 定义了却没人用的档 = 噪音。阶梯的意义在于「每一档都有职责」，
    # 一档没人用就说明当初是照着数轴凑的，不是照着职责定的。
    tokens_css = (REPO / "app/static/css/tokens.css").read_text(encoding="utf-8")
    defined = set(re.findall(r"^\s*(--(?:fs|lh)-[\w-]+)\s*:", tokens_css, re.M))
    used = {m for f in CSS_FILES
            for m in re.findall(r"var\((--(?:fs|lh)-[\w-]+)",
                                (REPO / f).read_text(encoding="utf-8"))}
    orphans = sorted(defined - used)
    if orphans:
        print(f"{len(orphans)} 个排版令牌定义了但没人用：{'、'.join(orphans)}")
        print("要么派活给它，要么删掉 —— 没有职责的档就是下一次「51 种取值」的种子。")
        return 1

    fs = found["font-size"]
    lh = found["line-height"]
    print(f"OK   font-size {sum(len(v) for v in fs.values())} 处，全部走令牌"
          f"（{len([v for v in fs if v.startswith('var(')])} 种引用）")
    print(f"OK   line-height {sum(len(v) for v in lh.values())} 处，全部走令牌"
          f"（{len([v for v in lh if v.startswith('var(')])} 种引用）")
    print(f"OK   例外 {len(ALLOW)} 条，均有理由")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="排版令牌审计")
    ap.add_argument("--census", action="store_true", help="逐处清点（值 → 次数 → 用在哪）")
    ap.add_argument("--summary", action="store_true", help="只看取值分布")
    args = ap.parse_args()
    if args.census:
        return census()
    if args.summary:
        return summary()
    return check()


if __name__ == "__main__":
    sys.exit(main())
