# -*- coding: utf-8 -*-
"""查**数据库内容**里的汉字有没有被字体子集覆盖。

    python scripts/check_content_fonts.py

为什么 `check_fonts.py` 不够：它扫的是**模板**里的字。而站上大量文字在数据库里 ——
公告正文、作品简介、活动说明、获奖记录里的队员姓名。人名尤其容易出生僻字：
正文字表是 GB2312 一级字（3755 个常用字），二级字（3008 个人名用字）不在里面。

缺字的后果是那一个字回退系统黑体 —— 一个名字里混两种字形，而页面照常渲染、
控制台干净。真踩到过：导入 15 条获奖记录带进 5 个二级字（昊 晗 淏 琛 蹇）。

**怎么修**：把报出来的字加进 `scripts/build_fonts.py` 的 `CONTENT_EXTRA`，
然后重跑 build_fonts（要带 `--body`，正文两档才会重建）。
不要整套加二级字 —— 那会让正文从 2071KB 涨到约 3700KB，而字体预算是 3100KB。

**dev 库与生产库的内容不一样**，所以这个脚本报的是「当前这个库」的情况。
导入内容之后跑一次；生产上也可以跑（`docker compose exec app ...`）。
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

import django  # noqa: E402

django.setup()

FONTS_DIR = REPO / "app" / "static" / "fonts"

# 正文两档是**所有**数据库文字的落点，所以只查它们。
# 标题字（得意黑）按模板取字，数据库内容压根不走它 —— `.hn-title` / `.news-card-title`
# 这些都没写 font-family，继承的是正文。查它会报一堆假警。
BODY_FONTS = ("SourceHanSansCN-Regular-subset.woff2", "SourceHanSansCN-Bold-subset.woff2")

failures: list[str] = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def collect() -> dict[str, set[str]]:
    """把各模型会渲染出来的文本字段收成 {来源: 字集}。

    只收**会出现在页面上**的字段：不收 slug、不收内部备注（`interview_note` 是
    仅管理组可见，但驾驶舱也是页面，所以照收）。
    """
    from django.apps import apps

    # (app.Model, 字段名...)。加了新的内容模型就往这里补一行。
    TARGETS = [
        ("news.Post", "title", "body"),
        ("news.Honor", "title", "contest", "awardee", "note"),
        ("projects.Project", "name", "summary"),
        ("events.Event", "title", "description", "location"),
        ("files.Resource", "title", "description"),
        ("accounts.User", "real_name", "public_bio", "college"),
        ("accounts.Position", "name", "blurb"),
        ("accounts.Medal", "name", "description"),
        ("recruitment.Campaign", "name", "intro"),
        ("recruitment.Application", "skills", "self_intro",
         "first_impression", "motto", "interests_other", "heard_from_other"),
        ("core.SiteConfig", "site_name", "site_name_en"),
    ]
    out: dict[str, set[str]] = {}
    for dotted, *fields in TARGETS:
        try:
            model = apps.get_model(dotted)
        except LookupError:
            print(f"  （跳过 {dotted}：这个模型不在了）")
            continue
        # 字段名先对着模型核一遍。写错一个的后果是 `values_list` 直接抛
        # FieldError 把整个脚本带崩 —— 而这个脚本的价值在于「跑得完并报出缺字」。
        real = {f.name for f in model._meta.get_fields() if hasattr(f, "attname")}
        bad = [f for f in fields if f not in real]
        if bad:
            failures.append(f"{dotted} 的字段名写错了：{', '.join(bad)}")
            print(f"  FAIL {dotted} 字段名不存在：{', '.join(bad)}")
            fields = [f for f in fields if f in real]
            if not fields:
                continue
        chars: set[str] = set()
        for row in model.objects.values_list(*fields):
            for value in row:
                if isinstance(value, str):
                    chars.update(c for c in value if "\u3400" <= c <= "\u9fff")
        if chars:
            out[dotted] = chars
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        print("需要 fonttools：python -m pip install fonttools brotli"
              "（开发工具，不进 requirements）")
        return 2

    by_source = collect()
    all_chars: set[str] = set()
    print("数据库里会渲染出来的汉字")
    for source, chars in sorted(by_source.items()):
        print(f"  {source:32s} {len(chars):5d} 字")
        all_chars |= chars
    check(bool(all_chars), "库里真的有中文内容（不然这一步空跑）", f"{len(all_chars)} 字")
    if not all_chars:
        print("\n（这个库是空的，换个有内容的库再跑）")
        return 1

    print("\n正文两档的覆盖")
    for fname in BODY_FONTS:
        path = FONTS_DIR / fname
        if not path.exists():
            check(False, f"{fname} 存在")
            continue
        cmap = {chr(cp) for cp in TTFont(str(path), fontNumber=0).getBestCmap()}
        missing = sorted(all_chars - cmap)
        check(not missing, f"**{fname} 覆盖了全部内容用字**",
              f"缺 {len(missing)} 字：{''.join(missing)}" if missing else f"{len(all_chars)} 字全覆盖")
        if missing:
            # 直接给出能粘进 build_fonts.py 的形式
            print(f"       把这些加进 scripts/build_fonts.py 的 CONTENT_EXTRA：\"{''.join(missing)}\"")
            for source, chars in sorted(by_source.items()):
                hit = sorted(set(missing) & chars)
                if hit:
                    print(f"       来自 {source}：{''.join(hit)}")

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("数据库内容用字全部有字形")
    return 0


if __name__ == "__main__":
    sys.exit(main())
