# -*- coding: utf-8 -*-
"""
CSS 声明级差异审计：拆分 / 重构样式表时证明"一条规则都没丢"。

背景：site.css 长到 1400 行后要拆成 tokens/core/home 三层，纯结构调整不该
改变任何视觉。截图比对对这件事的保障很弱（渲染差一像素就报警，真丢了一条
冷门规则却可能截不到），所以直接在声明层面比。

用法：
    # 看一个文件的统计
    python scripts/css_audit.py --dump app/static/css/core.css

    # 重构前后比对（after 可以给多个文件，按层叠顺序排列）
    python scripts/css_audit.py \
        --before /tmp/core-before.css \
        --after app/static/css/tokens.css app/static/css/core.css

    # 忽略预期内的新增属性
    python scripts/css_audit.py --before a.css --after b.css --ignore-prop content

退出码：0 表示无差异，1 表示有差异（可直接用在 pre-commit 或 CI 里）。

能力边界（照实说，别把它当银弹）：
- 比的是「(@media 上下文, 选择器, 属性) -> 最终生效值」，同一上下文里同一
  选择器重复声明同一属性时取最后一条，与浏览器一致。
- 不做跨选择器的层叠/优先级推演。把 `.a{color:red}` 改成 `#id .a{color:red}`
  这类优先级变化本工具看不出来，只能靠人眼和浏览器。
- 不解析 CSS 嵌套（本仓库没用），遇到嵌套会按未知块跳过并在报告里点名。
"""
import argparse
import re
import sys
from collections import OrderedDict
from pathlib import Path

# 不需要拆进选择器的 at-rule：整块作为独立上下文对待
BLOCK_AT_RULES = ("@media", "@supports", "@container", "@layer")
# 直接装声明、没有选择器的 at-rule
FLAT_AT_RULES = ("@font-face", "@page", "@property", "@view-transition")


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def split_top_level(body: str) -> list[str]:
    """按大括号配对把一段 CSS 切成若干顶层片段（规则或 at-rule 块）。"""
    chunks: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(body):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                chunks.append(body[start:i + 1])
                start = i + 1
        elif ch == ";" and depth == 0:
            # 顶层的 @import / @charset 之类，无块
            chunk = body[start:i + 1].strip()
            if chunk:
                chunks.append(chunk)
            start = i + 1
    tail = body[start:].strip()
    if tail:
        chunks.append(tail)
    return [c.strip() for c in chunks if c.strip()]


def norm_selector(selector: str) -> str:
    """归一化选择器：压空白、逗号分组排序，让书写顺序变化不产生假差异。"""
    selector = re.sub(r"\s+", " ", selector).strip()
    parts = [re.sub(r"\s*([>+~])\s*", r" \1 ", p.strip()) for p in selector.split(",")]
    parts = [re.sub(r"\s+", " ", p).strip() for p in parts if p.strip()]
    return ", ".join(sorted(parts))


def norm_value(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip().rstrip(";").strip()
    # 逗号前后的空白无语义：min(1240px,92%) 与 min(1240px, 92%) 视为同一取值
    value = re.sub(r"\s*,\s*", ", ", value)
    # 去掉数值里可选的前导 0（.5 与 0.5 等价），统一小写十六进制色值
    value = re.sub(r"(?<![\w.])0+(\.\d+)", r"\1", value)
    value = re.sub(r"#([0-9a-fA-F]{3,8})\b", lambda m: "#" + m.group(1).lower(), value)
    return value


def parse_declarations(block: str) -> list[tuple[str, str]]:
    """解析一个 {} 里的声明列表。跳过嵌套块（本仓库不用 CSS 嵌套）。"""
    decls: list[tuple[str, str]] = []
    depth = 0
    buf = ""
    for ch in block:
        if ch == "{":
            depth += 1
            buf += ch
        elif ch == "}":
            depth -= 1
            buf += ch
        elif ch == ";" and depth == 0:
            if ":" in buf:
                prop, _, val = buf.partition(":")
                decls.append((prop.strip().lower(), norm_value(val)))
            buf = ""
        else:
            buf += ch
    if ":" in buf and buf.strip():
        prop, _, val = buf.partition(":")
        decls.append((prop.strip().lower(), norm_value(val)))
    return decls


def walk(chunks: list[str], context: str, out: "OrderedDict", warnings: list[str], flat_seq: dict) -> None:
    for chunk in chunks:
        if not chunk.endswith("}"):
            # 无块 at-rule，如 @import
            key = (context, "@statement", norm_value(chunk))
            out[key] = ""
            continue

        head, _, rest = chunk.partition("{")
        head = head.strip()
        body = rest[:rest.rfind("}")]

        if head.startswith(BLOCK_AT_RULES):
            inner_ctx = f"{context} || {norm_value(head)}" if context else norm_value(head)
            walk(split_top_level(body), inner_ctx, out, warnings, flat_seq)
            continue

        if head.startswith("@keyframes") or head.startswith("@-webkit-keyframes"):
            name = norm_value(head)
            for stop in split_top_level(body):
                s_head, _, s_rest = stop.partition("{")
                s_body = s_rest[:s_rest.rfind("}")] if "}" in s_rest else s_rest
                sel = norm_selector(s_head)
                for prop, val in parse_declarations(s_body):
                    out[(f"{context} || {name}" if context else name, sel, prop)] = val
            continue

        if head.startswith(FLAT_AT_RULES):
            # 同名 at-rule 可以出现多次（多个 @font-face），用序号区分
            base = norm_value(head)
            idx = flat_seq.get((context, base), 0)
            flat_seq[(context, base)] = idx + 1
            sel = f"{base}#{idx}"
            for prop, val in parse_declarations(body):
                out[(context, sel, prop)] = val
            continue

        if head.startswith("@"):
            warnings.append(f"未识别的 at-rule，已跳过：{head[:60]}")
            continue

        if "{" in body:
            warnings.append(f"检测到嵌套块，已按平铺解析：{head[:60]}")

        sel = norm_selector(head)
        for prop, val in parse_declarations(body):
            out[(context, sel, prop)] = val


def parse_file(path: Path) -> tuple["OrderedDict", list[str]]:
    css = strip_comments(path.read_text(encoding="utf-8"))
    out: "OrderedDict" = OrderedDict()
    warnings: list[str] = []
    walk(split_top_level(css), "", out, warnings, {})
    return out, warnings


def parse_many(paths: list[Path]) -> tuple["OrderedDict", list[str]]:
    merged: "OrderedDict" = OrderedDict()
    all_warnings: list[str] = []
    for p in paths:
        decls, warnings = parse_file(p)
        for key, val in decls.items():
            merged[key] = val  # 后面的文件覆盖前面的，与 <link> 顺序一致
        all_warnings.extend(f"{p.name}: {w}" for w in warnings)
    return merged, all_warnings


def fmt(key: tuple) -> str:
    context, sel, prop = key
    prefix = f"[{context}] " if context else ""
    return f"{prefix}{sel} {{ {prop} }}"


def main() -> int:
    # Windows 下输出被管道接走时 stdout 会退回 GBK，中文报告直接乱码
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="CSS 声明级差异审计")
    ap.add_argument("--dump", type=Path, help="打印单个文件的解析统计")
    ap.add_argument("--before", type=Path, help="重构前的样式表")
    ap.add_argument("--after", type=Path, nargs="+", help="重构后的样式表（按层叠顺序）")
    ap.add_argument("--ignore-prop", action="append", default=[], help="忽略某个属性的差异，可重复")
    args = ap.parse_args()

    if args.dump:
        decls, warnings = parse_file(args.dump)
        selectors = {(c, s) for c, s, _ in decls}
        contexts = {c for c, _, _ in decls if c}
        print(f"{args.dump}：{len(decls)} 条声明 / {len(selectors)} 个选择器 / {len(contexts)} 个 at-rule 上下文")
        for w in warnings:
            print(f"  ! {w}")
        return 0

    if not args.before or not args.after:
        ap.print_help()
        return 2

    before, w_before = parse_file(args.before)
    after, w_after = parse_many(args.after)
    ignored = {p.lower() for p in args.ignore_prop}

    missing = [k for k in before if k not in after and k[2] not in ignored]
    added = [k for k in after if k not in before and k[2] not in ignored]
    changed = [
        (k, before[k], after[k])
        for k in before
        if k in after and before[k] != after[k] and k[2] not in ignored
    ]

    print(f"重构前：{len(before)} 条声明（{args.before.name}）")
    print(f"重构后：{len(after)} 条声明（{', '.join(p.name for p in args.after)}）")
    for w in w_before + w_after:
        print(f"  ! {w}")

    if missing:
        print(f"\n丢失 {len(missing)} 条：")
        for k in missing:
            print(f"  - {fmt(k)} = {before[k]}")
    if changed:
        print(f"\n取值变化 {len(changed)} 条：")
        for k, old, new in changed:
            print(f"  ~ {fmt(k)}\n      前: {old}\n      后: {new}")
    if added:
        print(f"\n新增 {len(added)} 条：")
        for k in added:
            print(f"  + {fmt(k)} = {after[k]}")

    if not (missing or changed or added):
        print("\n无差异：所有声明逐条一致。")
        return 0

    print(f"\n合计差异：丢失 {len(missing)} · 变化 {len(changed)} · 新增 {len(added)}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
