# -*- coding: utf-8 -*-
"""把招新 PPT 里的内嵌图全部挖出来，并记清每张图出现在**哪一页**。

    python scripts/dump_pptx.py              # 解包 + 出清单
    python scripts/dump_pptx.py --list       # 只打印清单，不写文件

pptx 就是一个 zip：图在 `ppt/media/`，每页的文字在 `ppt/slides/slideN.xml` 的
`<a:t>` 里。而「这一页用了哪几张图」要绕一道：`ppt/slides/_rels/slideN.xml.rels`
给出 `rId → ../media/xxx` 的映射，`slideN.xml` 里的 `r:embed="rIdN"` 说这一页
引用了哪些 rId，两边一join 就得到页码 → 图片。

**为什么页码这么重要**：一张证书照片单看往往认不出是哪一年、哪个赛事的哪一条 ——
但它所在那一页的正文写着。第一次挖这个 PPT 时没做这一步，于是只认出 13 张证书，
剩下二十多张不知道怎么归类就放过去了，直到用户说「至少有 30 多张」才发现。

产物落在 `.artsrc/ppt-dump/`（`.artsrc/` 整个在 .gitignore 里，母图不入库）。
分类结论写进 `docs/PPT素材清单.md`，那份才是入库的事实来源。

    python scripts/dump_pptx.py --verify-doc

把那份清单里提到的每一个 `imageNN` 拿回来对一遍：文件在不在、尺寸对不对得上。
**这一步不是形式主义** —— 清单里有六十多处编号引用，而「把 image67 写成 image76」
这种错不会以任何形式报错，只会让某条奖项配上别人的证书照。
它刻意不做成 Django 测试：`.artsrc/` 不入库，测试在别人的检出里必然失败。
"""
import argparse
import re
import shutil
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SRC = REPO / "2025科协招新.pptx"
OUT = REPO / ".artsrc" / "ppt-dump"

SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
MEDIA_RE = re.compile(r"^ppt/media/(.+)$")
TEXT_RE = re.compile(r"<a:t>(.*?)</a:t>", re.S)
# rels 里一条 Relationship 长这样：Id="rId3" ... Target="../media/image7.png"
REL_RE = re.compile(r'Id="([^"]+)"[^>]*?Target="\.\./media/([^"]+)"')
# 幻灯片里引用图片的地方：r:embed（普通图）与 r:link（外链图，本 PPT 里没有）
EMBED_RE = re.compile(r'r:(?:embed|link)="([^"]+)"')


def natural_key(name: str):
    """image10 要排在 image9 后面，按数字段排序而不是字典序。"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


DOC = REPO / "docs" / "PPT素材清单.md"


def verify_doc() -> int:
    """核对清单里引用的每个 imageNN 都真实存在。

    清单里有六十多处 `imageNN` 引用，把 `image67` 写成 `image76` 不会以任何形式
    报错，只会让某条奖项配上别人的证书照 —— 而那正是这份清单最不能出错的地方。
    """
    if not DOC.exists():
        print(f"找不到 {DOC.relative_to(REPO)}")
        return 1
    if not OUT.exists():
        print(f"还没解包，先跑一次不带参数的 dump_pptx.py（要 {OUT.relative_to(REPO)}）")
        return 1

    # 磁盘上叫 image67.jpeg / image72.png，清单里只写 image67 —— 按主干名建索引
    on_disk = {p.stem: p.name for p in OUT.iterdir() if p.is_file()}
    text = DOC.read_text(encoding="utf-8")
    refs = sorted(set(re.findall(r"\bimage\d+\b", text)), key=natural_key)

    missing = [r for r in refs if r not in on_disk]
    print(f"清单引用了 {len(refs)} 个编号，磁盘上有 {len(on_disk)} 个文件")
    for r in refs:
        mark = "OK  " if r in on_disk else "FAIL"
        print(f"  {mark} {r:12s} {on_disk.get(r, '（不存在）')}")
    print()
    if missing:
        print(f"{len(missing)} 个编号在 {OUT.relative_to(REPO)} 里找不到："
              + "、".join(missing))
        return 1
    # 反向也报一句：解包出来但清单一个字都没提的，就是漏判了
    unmentioned = sorted(set(on_disk) - set(refs), key=natural_key)
    print(f"清单里的编号全部存在。另有 {len(unmentioned)} 张没被逐个点名"
          f"（按整页归类的那些，见清单的「页面结构」与「不用的，按类分」两节）")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="从 pptx 里挖出全部内嵌图与每页文字")
    ap.add_argument("--src", default=str(DEFAULT_SRC), help="pptx 路径")
    ap.add_argument("--list", action="store_true", help="只打印清单，不写出文件")
    ap.add_argument("--verify-doc", action="store_true",
                    help="核对 docs/PPT素材清单.md 里引用的每个 imageNN 是否真实存在")
    args = ap.parse_args()

    if args.verify_doc:
        return verify_doc()

    src = Path(args.src)
    if not src.exists():
        print(f"找不到 {src}")
        print("这个 pptx 不入库（.gitignore 里），要重新取的话见 docs/荣誉数据来源.md")
        return 1

    try:
        from PIL import Image
    except ImportError:
        print("需要 Pillow：python -m pip install pillow（开发工具，不进 requirements）")
        return 2

    with zipfile.ZipFile(src) as z:
        names = z.namelist()

        # ---------- 每页的文字 ----------
        slides: dict[int, str] = {}
        for n in names:
            m = SLIDE_RE.match(n)
            if not m:
                continue
            xml = z.read(n).decode("utf-8", "replace")
            runs = [r.strip() for r in TEXT_RE.findall(xml) if r.strip()]
            slides[int(m.group(1))] = " ".join(runs)

        # ---------- 页码 → 图片 ----------
        # rels 与 slide 是两个文件，必须都读到才连得起来；缺 rels 的页就是没有图。
        used_by: dict[str, list[int]] = defaultdict(list)
        for no in sorted(slides):
            rels_name = f"ppt/slides/_rels/slide{no}.xml.rels"
            if rels_name not in names:
                continue
            rels = dict(REL_RE.findall(z.read(rels_name).decode("utf-8", "replace")))
            xml = z.read(f"ppt/slides/slide{no}.xml").decode("utf-8", "replace")
            for rid in dict.fromkeys(EMBED_RE.findall(xml)):   # 去重但保序
                target = rels.get(rid)
                if target:
                    used_by[target].append(no)

        # ---------- 导出图片 ----------
        media = sorted((n for n in names if MEDIA_RE.match(n)),
                       key=lambda n: natural_key(n.rsplit("/", 1)[-1]))
        if not args.list:
            OUT.mkdir(parents=True, exist_ok=True)
            for n in media:
                name = n.rsplit("/", 1)[-1]
                with z.open(n) as fsrc, open(OUT / name, "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst)

        rows = []
        for n in media:
            name = n.rsplit("/", 1)[-1]
            info = z.getinfo(n)
            try:
                with z.open(n) as f:
                    w, h = Image.open(f).size
            except Exception:
                w = h = 0          # emf/wmf 之类 Pillow 打不开的，尺寸留 0
            rows.append({
                "name": name,
                "w": w, "h": h,
                "kb": info.file_size / 1024,
                "slides": used_by.get(name, []),
            })

    # ---------- 打印 ----------
    print(f"来源 {src.name}  共 {len(slides)} 页 / {len(rows)} 张内嵌图")
    if not args.list:
        print(f"图已写到 {OUT.relative_to(REPO)}/")
    print()
    print(f"{'文件':22s} {'尺寸':>12s} {'体积':>9s}  出现在第几页")
    print("-" * 72)
    orphans = 0
    for r in rows:
        size = f"{r['w']}x{r['h']}" if r["w"] else "（非位图）"
        pages = "、".join(str(p) for p in r["slides"]) or "—（没有任何一页引用）"
        if not r["slides"]:
            orphans += 1
        print(f"{r['name']:22s} {size:>12s} {r['kb']:8.0f}K  {pages}")

    print()
    print("每页文字（用来给同页的图定年份与赛事）")
    print("-" * 72)
    for no in sorted(slides):
        imgs = [r["name"] for r in rows if no in r["slides"]]
        text = slides[no] or "（无文字）"
        print(f"\n== slide{no} ==  图：{'、'.join(imgs) if imgs else '无'}")
        print(text[:1200])

    print()
    print(f"小结：{len(rows)} 张图，其中 {orphans} 张没有任何一页引用"
          f"（母版/版式里的装饰，或者作者删了那一页但图还留在包里）")
    big = [r for r in rows if r["w"] and max(r["w"], r["h"]) >= 700]
    print(f"      长边 ≥700 的 {len(big)} 张 —— 证书要能读清字，低于这个数放到墙上是糊斑")
    return 0


if __name__ == "__main__":
    sys.exit(main())
