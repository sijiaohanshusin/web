# -*- coding: utf-8 -*-
"""校验页面重量与加载方式的预算。

为什么要一个脚本盯着：这套设计用了 GSAP + Lenis + three.js，**很容易在不知不觉
间把 365KB 的 three 拖到一个压根不需要 3D 的页面上** —— 页面照常渲染、控制台干净、
所有既有检查脚本全绿，只是每个访客多下 365KB。同类的还有「某一页忘了 defer」
「新加的图忘了 lazy」「字体没 preload 于是首屏大标题先用系统黑体画一遍」。
这些都不会报错，只会慢。

判据取「浏览器自己报的数」：`performance.getEntriesByType('resource')` 的
`decodedBodySize`（要解析多少字节）与 `initiatorType`（谁拉来的）。
**dev 服务器不压缩**，所以脚本另外从仓库里的文件现算一遍 gzip 后的大小，用来对
生产做估算 —— 断言分两套，别把两个数混着看。

跑法：python scripts/check_perf.py
"""
import gzip
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

from shoot import PORT, DevServer  # noqa: E402

STATIC = REPO / "app" / "static"
failures = []

# 每页的「解析预算」（KB，未压缩）。定这几个数的依据是当前实测值 + 一点余量，
# 目的不是压到最小，而是**下一次多拖进来一个大库时当场红掉**。
#
# 2026 排版增强期把内页 css 从 150 上调到 175：这个站主要用来展示，用户已明确
# 「展示效果优先于加载时间，体积不设硬上限」（重复访问有一年 immutable 缓存）。
# 涨的这一段几乎全是 tokens.css 里的设计说明注释 —— 未压缩当然要算进来，但上线
# 走 gzip 之后注释压得极狠，线上实收增量是个位数 KB（跑 ops/verify.sh 看实收值）。
# **上调而不是删掉**：这条断言的作用从此变成「防止无意中多拖进来一份没人用的
# 东西」，删了就没人看着了。
#
# 第二次上调（内页 175 → 190，首页 215 → 230）：美术资产接入那一批把 core.css /
# tokens.css 又推到了 175.0 —— 正好卡在上一版的预算上，下一行 CSS 就会红。
# 预算贴着实测值没有意义：它要么每加一条规则就要改一次（于是没人当它是约束），
# 要么就把人逼去删注释（而注释是这个项目最值钱的部分）。留 15KB 余量，够这一轮
# 剩下的排版工作用，同时仍然拦得住「误引入一份 40KB 的第三方样式表」这种事。
BUDGETS = {
    # 首页比别人重 750KB，全部是 three（three.module 365 + three.core 385，两个不是
    # 重复：module 是在 core 之上再加渲染器那一层）。它服务的是分镜 01 那块 3D 电路板 ——
    # 首页的正片主体。刻意让它在开场遮罩那几秒里下完（「首访可以慢」是明确约束），
    # 而不是等滚到分镜 01 才现下、导致 3D 迟一步弹进来把「逐层制造」那段叙事打断。
    # gzip 之后这 750KB 约 190KB。**没有 WebGL / 减动效时压根不下**，下面有断言钉住。
    # font 从 500 提到 3100：正文两档中文（GB2312 一级字全集）约 2MB，
    # 第二声音（宋体，按模板取字）461KB。见 build_fonts.py 与 tokens.css 的注释。
    # 首页的 css 比内页多一份 home.css（分镜专属）+ lenis.css
    #
    # total 4700 → 4740：这 40KB 是**刻意**留给第一屏那张氛围图的
    # （`.nf-hero::before` 的 `--hero-art`，工单在 docs/美术资产清单.md 第三批）。
    # 暗场氛围图的 webp 极小 —— 第二批七张 2560x860 的页头图压完只有 4.6~9.2KB，
    # 首屏这张 1920x1440 拿替身图实测 13KB —— 但上调前实测已经是 4672/4700，
    # **只剩 28KB**。不上调就是把它硬挤进那道缝里，下一个人再也没有余量。
    # 这条预算的职责是「别再无意中多拖进来一个大件」，一张刻意加的首屏图
    # 不属于它要拦的东西；而把它悄悄挤进去才是真的把预算变成摆设。
    #
    # css 230 → 245：接完首屏图之后实测 227/230，**余量只剩 3KB**，而上面那段
    # 注释自己写的是「留 15KB 余量，够这一轮剩下的排版工作用」—— 也就是按项目
    # 自己的标准，余量已经用完了。涨的这一段全是 home.css 里那两段设计说明
    # （竖屏断点为什么按画框比例、三档取色的实测对比度），gzip 之后压得极狠：
    # 未压缩 243KB 对应 gzip 77KB。**上调而不是删注释** —— 理由同上一段。
    #
    # ---------------------------------------------------------------------
    # font 3100 → 4700，各页 total 跟着抬一档。**下面五条改动是同一个原因**：
    # 正文字表从 GB2312 一级字（3755）扩到**全集（一级+二级，6763）**，两档
    # 思源黑体从 1030KB 各涨到 1841 / 1864KB，字体合计 2932 → 4566KB。
    #
    # 为什么值这 1.6MB：**二级字区就是人名用字区**。站上大量文字在数据库里 ——
    # 公告正文、作品简介、获奖记录里的队员姓名 —— 模板扫不到，用量不可预测。
    # 真踩到过：导入 15 条获奖记录带进 5 个二级字（昊 晗 淏 琛 蹇），每个名字里
    # 混一个系统黑体的字，页面照常渲染、控制台干净。手工策展一份「内容生僻字」
    # 清单试过，但那等于「每加一个人名都要记得改字体」，下一次必然忘。
    # 用量不可预测的地方按全集收，不按用量收。
    #
    # 代价看清楚了再涨的：gzip 之后字体 3856KB，首访「代码 + 字体」4007KB。
    # woff2 已经自压缩，所以这 1.6MB 是实打实的流量。取舍依据是站点的既有约束
    # 「展示效果优先于加载时间」+ 重复访问有一年 immutable 缓存，且用户明确许可。
    # `scripts/check_content_fonts.py` 负责盯住「库里的字有没有字形」。
    #
    # total 6450 → 6650：图片走廊的六格全部换成协会自有的实拍照（原来三格是空
    # 焊盘占位、一个字节都不下）。三张新照片合计 265KB —— 合影 126 + 颁奖 79 +
    # 赛场调试 60，都是 webp q78，逐张对比过 q84 看不出差别（见 build_photos.py）。
    # 这一项换来的是首页从「有三个空框」变成「六张真照片」，正是招新页最该有的
    # 东西，而且它们全在首屏之外、全是 lazy，不占首屏时间。
    # 实测 6610，留 90KB 余量 —— 一张走廊照就是 80~130KB，所以**再往走廊里加图
    # 就要在这里重新定基线并写清换来了什么**，不要顺手把数字往上顶。
    "/": {"total": 6700, "js": 1150, "css": 245, "font": 4700},
    "/news/": {"total": 5100, "js": 200, "css": 190, "font": 4700},
    "/recruit/": {"total": 6800, "js": 220, "css": 190, "font": 4700},
    "/works/": {"total": 5100, "js": 200, "css": 190, "font": 4700},
    "/accounts/register/": {"total": 5100, "js": 210, "css": 190, "font": 4700},
}

# 只有首页的分镜 01 会 import three。别的页面拉到它就是纯浪费。
HEAVY_ONLY_ON_HOME = ["three.module", "three.core", "SVGLoader", "BufferGeometryUtils",
                      "logo-3d", "chart.umd"]

RESOURCES = """
() => {
    const kind = (e) => {
        const n = e.name;
        if (/\\.css(\\?|$)/.test(n)) return 'css';
        if (/\\.m?js(\\?|$)/.test(n)) return 'js';
        if (/\\.woff2?(\\?|$)/.test(n)) return 'font';
        if (/\\.(png|jpe?g|webp|gif|svg|avif)(\\?|$)/.test(n)) return 'img';
        if (/\\.(mp4|webm)(\\?|$)/.test(n)) return 'video';
        return 'other';
    };
    const rows = document.getElementsByTagName ? performance.getEntriesByType('resource') : [];
    return {
        items: rows.map(e => ({
            name: e.name.replace(location.origin, ''),
            kind: kind(e),
            // dev 不压缩，decoded 就是真实体积；生产的估算在 Python 侧另算
            bytes: e.decodedBodySize || e.transferSize || 0,
            init: e.initiatorType,
            start: Math.round(e.startTime),
        })),
        dcl: Math.round(performance.timing
              ? performance.timing.domContentLoadedEventEnd - performance.timing.navigationStart
              : 0),
    };
}
"""

# head 里的阻塞项。样式表天然阻塞渲染；脚本只要没有 defer/async/module 就阻塞解析。
BLOCKING = """
() => {
    const head = document.head;
    const css = [...head.querySelectorAll('link[rel=stylesheet]')]
        .map(l => l.getAttribute('href').split('/').pop());
    const js = [...head.querySelectorAll('script[src]')]
        .filter(s => !s.defer && !s.async && s.type !== 'module')
        .map(s => s.getAttribute('src').split('/').pop());
    const preloads = [...head.querySelectorAll('link[rel=preload]')]
        .map(l => ({ as: l.getAttribute('as'),
                     file: l.getAttribute('href').split('/').pop() }));
    const bodyBlocking = [...document.body.querySelectorAll('script[src]')]
        .filter(s => !s.defer && !s.async && s.type !== 'module')
        .map(s => s.getAttribute('src').split('/').pop());
    return { css, js, preloads, bodyBlocking };
}
"""

IMAGES = """
() => {
    const vh = window.innerHeight;
    const imgs = [...document.querySelectorAll('img')];
    return imgs.map(i => {
        const r = i.getBoundingClientRect();
        return { src: (i.getAttribute('src') || '').split('/').pop(),
                 top: Math.round(r.top + window.scrollY),
                 lazy: i.getAttribute('loading') === 'lazy',
                 decoding: i.getAttribute('decoding') || '' };
    });
}
"""


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def gz(path: Path) -> int:
    return len(gzip.compress(path.read_bytes(), 6))


def report_gzip():
    """生产是 nginx gzip 直出，所以把仓库里那几个大件的压缩后体积摆出来。

    woff2 内部已经是 Brotli，再 gzip 基本不动 —— 所以字体那两个数就是真实网络体积。
    """
    print("\n生产估算：nginx gzip 之后这几个大件到底多大（woff2 已自压缩，不再受益）")
    groups = {
        "vendor JS": sorted((STATIC / "vendor").glob("*.js")),
        "站内 JS": sorted((STATIC / "js").glob("*.js")) + sorted((STATIC / "js" / "scenes").glob("*.js")),
        "CSS": sorted((STATIC / "css").glob("*.css")),
        "字体": sorted((STATIC / "fonts").glob("*.woff2")),
    }
    for name, files in groups.items():
        raw = sum(f.stat().st_size for f in files)
        small = sum(gz(f) for f in files)
        print(f"  {name:<9} {raw / 1024:7.0f} KB → gzip {small / 1024:6.0f} KB"
              f"（{small / max(raw, 1):.0%}）")
    # 首页真正会下的那一套（不含按需的 three / logo-3d）
    always = [
        STATIC / "css" / "tokens.css", STATIC / "css" / "core.css",
        STATIC / "css" / "home.css", STATIC / "vendor" / "lenis.css",
        STATIC / "vendor" / "gsap.min.js", STATIC / "vendor" / "ScrollTrigger.min.js",
        STATIC / "vendor" / "SplitText.min.js", STATIC / "vendor" / "lenis.min.js",
        STATIC / "js" / "motion-core.js", STATIC / "js" / "site.js",
        STATIC / "js" / "preloader.js", STATIC / "js" / "view-transitions.js",
        STATIC / "js" / "video-slots.js", STATIC / "js" / "home.js",
        STATIC / "js" / "hero-field.js",
        STATIC / "fonts" / "JetBrainsMono-subset.woff2",
        STATIC / "fonts" / "SmileySans-subset.woff2",
        STATIC / "fonts" / "SourceHanSansCN-Regular-subset.woff2",
        STATIC / "fonts" / "SourceHanSansCN-Bold-subset.woff2",
        STATIC / "fonts" / "SourceHanSerifCN-SemiBold-subset.woff2",
        STATIC / "fonts" / "ESTADigits.woff2",
    ]
    missing = [p.name for p in always if not p.exists()]
    total = sum(gz(p) for p in always if p.exists())
    check(not missing, "首页那套固定资源都在", ", ".join(missing))
    print(f"  → 首页首访的代码 + 字体合计 gzip 约 {total / 1024:.0f} KB"
          f"（其中字体 {sum(gz(p) for p in always[-6:]) / 1024:.0f} KB）")
    # 预算从 900KB 提到 3000KB：正文两档自托管中文字体占了约 2MB。
    # 这是明确的用体积换效果（用户口径：展示效果优先于加载时间，重复访问有一年
    # immutable 缓存 + 前面挂 EdgeOne）。**woff2 本身已经是 brotli 压缩过的**，
    # 所以这里 gzip 前后几乎一样，2MB 就是 2MB。
    # 上调而不是删掉：它现在的职责是「别再无意中多拖进来一个大件」。
    # 3500 → 4200：正文字表扩到 GB2312 全集，字体 gzip 后从 2425 涨到 3856KB，
    # 这一项实测 4007KB。原因与取舍见上面 BUDGETS 里那段（同一次改动）。
    check(total / 1024 <= 4200,
          "首页首访「代码 + 字体」在 4200KB 预算内（不含图片与按需的 3D）",
          f"{total / 1024:.0f} KB")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    import django

    django.setup()
    report_gzip()

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        base = f"http://127.0.0.1:{PORT}"
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = ctx.new_page()
        bad = []
        errors = []
        page.on("requestfailed", lambda r: bad.append(f"failed {r.url}"))
        page.on("response",
                lambda r: bad.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # ---------------- 加载方式 ----------------
        print("\n加载方式：阻塞项必须是清单上那几个，多一个都要有理由")
        page.goto(base + "/", wait_until="load")
        page.wait_for_function(
            "() => !document.documentElement.classList.contains('esta-pre-lock')", timeout=20000)
        b = page.evaluate(BLOCKING)
        check(b["js"] == ["view-transitions.js"],
              "**head 里只有 view-transitions.js 一个阻塞脚本**"
              "（它刻意不 defer，pagereveal 等不起）", str(b["js"]))
        check(not b["bodyBlocking"], "body 里的脚本全都 defer 了", str(b["bodyBlocking"]))
        check(len(b["css"]) <= 4, "阻塞渲染的样式表不超过 4 张", str(b["css"]))
        fonts_pre = sorted(x["file"] for x in b["preloads"] if x["as"] == "font")
        check(len(fonts_pre) == 6,
              "**六个自托管字体都 preload 了**（少一个，那一档文字就会先用别的字体画一遍再跳）",
              str(fonts_pre))

        # ---------------- 字体真的早早开始下 ----------------
        r = page.evaluate(RESOURCES)
        font_items = [i for i in r["items"] if i["kind"] == "font"]
        check(len(font_items) == 6, "六个字体都真的被下载了", str([i["name"] for i in font_items]))
        for i in font_items:
            check(i["init"] == "link",
                  f"{i['name'].split('/')[-1]} 是 preload 拉的（不是等 CSS 解析才发现）",
                  i["init"])

        # ---------------- 每页预算 ----------------
        print("\n每页解析预算（dev 不压缩，这里量的是「浏览器要解析多少字节」）")
        print("（每页都开一个新 context：共用一个的话字体第二页起就命中缓存，"
              "量出来 1KB，那条预算就再也不可能红了）")
        for url, budget in BUDGETS.items():
            # 预算说的是「首访要下多少」，所以每页都要一个干净的缓存
            pctx = browser.new_context(viewport={"width": 1440, "height": 1000})
            ppage = pctx.new_page()
            ppage.on("requestfailed", lambda r: bad.append(f"failed {r.url}"))
            ppage.on("response",
                     lambda r: bad.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
            ppage.on("pageerror", lambda e: errors.append(str(e)))
            ppage.goto(base + url, wait_until="load")
            ppage.wait_for_function(
                "() => !document.documentElement.classList.contains('esta-pre-lock')",
                timeout=20000)
            ppage.wait_for_timeout(600)
            r = ppage.evaluate(RESOURCES)
            by = {}
            for i in r["items"]:
                by[i["kind"]] = by.get(i["kind"], 0) + i["bytes"]
            total = sum(by.values()) / 1024
            print(f"\n  {url}  共 {len(r['items'])} 个请求 · 合计 {total:.0f} KB · "
                  f"DCL {r['dcl']}ms")
            print("      " + " · ".join(f"{k} {v / 1024:.0f}KB" for k, v in sorted(by.items())))
            check(total <= budget["total"], f"{url} 总解析量在预算内",
                  f"{total:.0f} / {budget['total']} KB")
            for kind in ("js", "css", "font"):
                got = by.get(kind, 0) / 1024
                check(got <= budget[kind], f"{url} {kind} 在预算内",
                      f"{got:.0f} / {budget[kind]} KB")

            # three 只该出现在首页
            if url != "/":
                heavy = [i["name"] for i in r["items"]
                         if any(h in i["name"] for h in HEAVY_ONLY_ON_HOME)]
                check(not heavy,
                      f"**{url} 没有拖进只有首页才用的重型库**（three 一个人就 365KB）",
                      ", ".join(heavy))
            # 字体是每页都要下的大件，顺手确认这一页真的把四个都下了 ——
            # 不然「font 在预算内」在缓存命中时会以 1KB 轻松通过、等于没测
            nfont = len([i for i in r["items"] if i["kind"] == "font"])
            check(nfont == 6, f"{url} 这一页真的下了六个字体（不是缓存命中）",
                  f"{nfont} 个")
            pctx.close()

        # ---------------- 降级路径不该白下 750KB ----------------
        print("\n减动效偏好：3D 不跑，那 750KB 的 three 就不该下")
        print("（这条最容易悄悄坏掉：把 import() 提到能力判断之前，降级用户照样付全部流量）")
        rctx = browser.new_context(viewport={"width": 1440, "height": 1000},
                                   reduced_motion="reduce")
        rpage = rctx.new_page()
        rpage.goto(base + "/", wait_until="load")
        rpage.wait_for_function(
            "() => !document.documentElement.classList.contains('esta-pre-lock')", timeout=20000)
        rpage.wait_for_timeout(1200)
        rr = rpage.evaluate(RESOURCES)
        heavy = [i["name"] for i in rr["items"]
                 if any(h in i["name"] for h in HEAVY_ONLY_ON_HOME)]
        rjs = sum(i["bytes"] for i in rr["items"] if i["kind"] == "js") / 1024
        check(not heavy, "**减动效下没有下载 three / logo-3d**", ", ".join(heavy))
        check(rjs <= 220, "减动效下的 JS 量回到内页水平", f"{rjs:.0f} KB")
        rctx.close()

        # ---------------- 图片加载策略 ----------------
        print("\n图片：首屏之外一律 lazy，且都写了 decoding")
        page.goto(base + "/recruit/", wait_until="load")
        page.wait_for_timeout(600)
        imgs = page.evaluate(IMAGES)
        below = [i for i in imgs if i["top"] > 1000]
        check(len(below) > 20, "新生指南上确实有一大批首屏外的图（不然下面那条空跑）",
              f"{len(below)} 张")
        not_lazy = [i["src"] for i in below if not i["lazy"]]
        check(not not_lazy, "**首屏之外的图全都 lazy**", ", ".join(not_lazy[:5]))

        page.goto(base + "/", wait_until="load")
        page.wait_for_function(
            "() => !document.documentElement.classList.contains('esta-pre-lock')", timeout=20000)
        page.wait_for_timeout(400)
        himgs = page.evaluate(IMAGES)
        no_dec = [i["src"] for i in himgs if not i["decoding"]]
        check(not no_dec, "首页每张图都写了 decoding（解码不占主线程）",
              ", ".join(no_dec[:5]))

        check(not bad, "全程没有失败请求 / 4xx / 5xx", "; ".join(bad[:3]))
        check(not errors, "全程无未捕获异常", "; ".join(errors[:2]))
        ctx.close()
        browser.close()

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("性能预算全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
