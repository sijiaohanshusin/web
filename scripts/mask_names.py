# -*- coding: utf-8 -*-
"""姓名脱敏：保留首尾，中间用 `*` 替掉。

    python scripts/mask_names.py 李小明 张伟 "Li Xiaoming"
    python scripts/mask_names.py --check 李*明        # 判断一个串是不是已经脱敏过

    李小明        → 李*明
    张伟          → 张*
    欧阳明日      → 欧**日
    Li Xiaoming   → Li X******g

**下面所有示例都是虚构名。** 拿真人的名字当脱敏规则的示例，本身就是泄漏 ——
第一版的 docstring 与自测用例全用了名单里的真名，`--scan` 一跑就把这个文件
自己报出来了（那次它没报，是因为文件还没 git add，见 `_repo_files` 的注释）。

**为什么必须在「写进仓库之前」就脱敏，而不是渲染时脱敏**：这个仓库是公开的
（`sijiaohanshusin/web`，而且已经被 fork 过），`ops/deploy.sh` 也是靠公开 tarball
拉代码的。真名一旦进了 `import_honors.py` 就等于发布了 —— 渲染时脱敏只能挡住网页
那一层，挡不住 git。所以**真名只留在 `.artsrc/`（不入库），仓库里从头到尾只有
脱敏后的串**。

`news/tests.py` 里有一条独立的断言扫 `HONORS` 的 `awardee`：凡是 ≥2 字的姓名都必须
带 `*`。它刻意不 import 这个模块、自己重写一遍判据 —— 拿同一个函数去验同一个函数
的输出，等于什么都没验。

**指导教师不脱敏。** 竞赛证书上的指导教师是职务署名，学院公众号发获奖通报时也
是指名写的（`image45` 就是一例）。这是一处判断，不是漏做；要改就把它们也过一遍
这个函数。
"""
import argparse
import re
import sys

# 一个「姓名」的判据：连续的中日韩统一表意文字，或连续的拉丁字母。
# 用来在一段话里找出需要脱敏的部分，也用来做校验。
CJK = r"\u4e00-\u9fff"
NAME_RUN = re.compile(f"[{CJK}]{{2,}}|[A-Za-z]{{2,}}")


def mask_token(tok: str) -> str:
    """单个词：首尾保留，中间打星。两个字的只保留第一个字。"""
    if len(tok) <= 1:
        return tok
    if len(tok) == 2:
        return tok[0] + "*"
    return tok[0] + "*" * (len(tok) - 2) + tok[-1]


def mask(name: str) -> str:
    """一个姓名。

    带空格的按罗马字处理：**第一段是姓，整段保留**，其余各段按 `mask_token`。
    「Li Xiaoming」→「Li X******g」。不这么分的话姓也会被打星，
    而姓本身不是识别到个人的那一部分。
    """
    name = name.strip()
    if not name:
        return name
    if " " in name:
        head, *rest = name.split()
        return " ".join([head] + [mask_token(t) for t in rest])
    return mask_token(name)


def mask_list(names: str, sep: str = "、") -> str:
    """一串用「、」隔开的姓名。荣誉墙的 `awardee` 就是这个形状。"""
    return sep.join(mask(n) for n in names.split(sep) if n.strip())


def is_masked(names: str, sep: str = "、") -> bool:
    """一串「、」分隔的姓名是不是都脱敏过了。

    **只适用于姓名列表这个形状**（`Honor.awardee` 就是），不要拿它扫自由文本 ——
    第一版就是那么写的（在整段里找「连续的汉字」），于是「电证字」「第」这类词
    全被当成漏掉的真名报出来，判据一多噪音就没人看了。备注里的指导教师姓名
    另有决定（见文件头），不在这条判据的管辖范围内。
    """
    for one in names.split(sep):
        one = one.strip()
        if not one:
            continue
        parts = one.split()
        # 罗马字名的姓整段保留，所以只看姓之后的部分
        targets = parts[1:] if len(parts) > 1 else parts
        for tok in targets:
            if len(tok) >= 2 and "*" not in tok:
                return False
    return True


ROSTER = REPO_ARTSRC = None   # 延迟到用的时候再算，见 _roster()


def _roster() -> dict[str, str]:
    """从 `.artsrc/honors-names.txt` 读出「真名 → 脱敏名」的对照表。

    底稿不入库，所以这张表只在本机存在 —— `--scan` / `--redact` 因此只能在有底稿的
    机器上跑。这是刻意的：把真名清单放进仓库来「方便检查有没有泄漏真名」，
    本身就是泄漏。
    """
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / ".artsrc" / "honors-names.txt"
    if not path.exists():
        return {}
    table: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for one in line.split("、"):
            one = one.strip()
            if one:
                table[one] = mask(one)
    # 长名先替换：否则「张伟」会先把「张伟华」的前两个字吃掉
    return dict(sorted(table.items(), key=lambda kv: -len(kv[0])))


def _repo_files():
    """仓库里会被提交的文本文件。走 `git ls-files` 而不是自己遍历 ——
    否则会把 .artsrc/ 底稿本身、.shots/ 截图、字体二进制全扫进来。"""
    import subprocess
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    # `--others --exclude-standard` 把**还没 git add 的新文件**也算进来，同时仍然
    # 尊重 .gitignore。只用 `ls-files` 的话新建的文件是隐形的 —— 第一版就是那样，
    # 于是这个脚本自己（当时还没入库）满是真名示例却一条都没报出来。
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others",
                          "--exclude-standard"], cwd=repo,
                         capture_output=True, text=True, encoding="utf-8")
    skip_suffix = {".webp", ".png", ".jpg", ".jpeg", ".gif", ".woff2", ".otf",
                   ".ttf", ".ico", ".pdf", ".sqlite3"}
    for rel in out.stdout.split("\0"):
        if not rel:
            continue
        path = repo / rel
        if path.suffix.lower() in skip_suffix or not path.is_file():
            continue
        yield rel, path


def scan_repo(fix: bool = False) -> int:
    """扫整个仓库有没有漏在外面的真名。

    **这是公开仓库的必备一步。** 真名不只可能出现在 `import_honors.py` 里 ——
    文档、注释、测试用例、提交信息模板，任何一处都行。逐个手改必然漏一个，
    而漏掉的那一个不会以任何形式报错。
    """
    table = _roster()
    if not table:
        print("没有找到 .artsrc/honors-names.txt（真名底稿），这台机器上没法扫。")
        return 2

    print(f"底稿里有 {len(table)} 个姓名，开始扫 git 跟踪的文本文件")
    hits: dict[str, list[tuple[int, str]]] = {}
    for rel, path in _repo_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found = [(real, masked) for real, masked in table.items() if real in text]
        if not found:
            continue
        lines = []
        for no, line in enumerate(text.splitlines(), 1):
            for real, _ in found:
                if real in line:
                    lines.append((no, line.strip()[:100]))
                    break
        hits[rel] = lines
        if fix:
            for real, masked in table.items():
                text = text.replace(real, masked)
            path.write_text(text, encoding="utf-8", newline="\n")

    if not hits:
        print("  OK   仓库里没有真名")
        return 0

    for rel, lines in hits.items():
        print(f"\n  {'已改' if fix else 'FAIL'} {rel}（{len(lines)} 处）")
        for no, line in lines[:6]:
            print(f"       {no}: {line}")
        if len(lines) > 6:
            print(f"       …… 另外 {len(lines) - 6} 处")
    print()
    if fix:
        print(f"改完 {len(hits)} 个文件。**再跑一次不带 --redact 的扫描确认干净**，"
              "然后看一遍 git diff —— 替换是纯文本替换，可能动到不该动的地方。")
        return 0
    print(f"{len(hits)} 个文件里还有真名。加 --redact 就地替换。")
    return 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="姓名脱敏：保留首尾，中间打星")
    ap.add_argument("names", nargs="*", help="姓名，可以是「张三、李四」这种整串")
    ap.add_argument("--check", action="store_true", help="改为判断给定串是否已脱敏")
    ap.add_argument("--file", help="从文件逐行读（每行一串），真名底稿放 .artsrc/ 不入库")
    ap.add_argument("--scan", action="store_true",
                    help="拿底稿扫整个仓库，报出还有真名的文件（公开仓库必查）")
    ap.add_argument("--redact", action="store_true",
                    help="连同 --scan 一起用：就地把真名替换成脱敏名")
    ap.add_argument("--self-test", action="store_true", help="跑一遍内置用例")
    args = ap.parse_args()

    if args.scan or args.redact:
        return scan_repo(fix=args.redact)

    if args.file:
        # 真名底稿只应该出现在 .artsrc/ 下（那个目录整个 gitignore）。
        # 拦一下手滑：从仓库里别的地方读，等于把真名放进了会被提交的位置。
        from pathlib import Path
        path = Path(args.file).resolve()
        if ".artsrc" not in path.parts:
            print(f"拒绝：{path} 不在 .artsrc/ 下。真名底稿不能放进会被提交的目录。")
            return 2
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            print(mask_list(line))
        return 0

    if args.self_test:
        # 全部虚构名，理由见文件头
        cases = [
            ("李小明", "李*明"),
            ("张伟", "张*"),
            ("欧阳明日", "欧**日"),
            ("Li Xiaoming", "Li X******g"),
            # 三个字母的名只遮得掉中间那一个 —— 和中文三字名「李*明」是同一条规则、
            # 同一个程度，不是漏做。要更狠就得改规则，那是另一个决定。
            ("Zhou Yan", "Zhou Y*n"),
        ]
        bad = 0
        for src, want in cases:
            got = mask(src)
            ok = got == want
            bad += not ok
            print(f"  {'OK  ' if ok else 'FAIL'} {src} → {got}"
                  + ("" if ok else f"（期望 {want}）"))
        # 整串
        got = mask_list("李小明、张伟、欧阳明日")
        want = "李*明、张*、欧**日"
        ok = got == want
        bad += not ok
        print(f"  {'OK  ' if ok else 'FAIL'} 整串 → {got}" + ("" if ok else f"（期望 {want}）"))
        # 校验器（只喂姓名列表）：真名判 False，脱敏串判 True
        for text, want_flag in [
            ("李小明", False),
            ("李*明", True),
            ("李*明、张*、欧**日", True),
            ("李*明、张伟、欧**日", False),           # 中间漏掉一个
            ("Li X******g、Zhou Y*n", True),
            ("Li Xiaoming", False),
            ("张*", True),                            # 两字名
            ("", True),                               # 没有获奖人的记录是允许的
        ]:
            got_flag = is_masked(text)
            ok = got_flag == want_flag
            bad += not ok
            print(f"  {'OK  ' if ok else 'FAIL'} is_masked({text!r}) = {got_flag}")
        print()
        print("全部通过" if not bad else f"{bad} 项未通过")
        return 1 if bad else 0

    if not args.names:
        ap.print_help()
        return 2
    for n in args.names:
        if args.check:
            print(f"  {'已脱敏' if is_masked(n) else '**还有真名**'}  {n}")
        else:
            print(f"  {n}  →  {mask_list(n)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
