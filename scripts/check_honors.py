# -*- coding: utf-8 -*-
"""校验荣誉墙：统计是数出来的、按年分组、公开边界、首页 08、驾驶舱录入。

这一页的风险和作品墙不太一样：

  1. **统计数字必须是数出来的**。「国家级 N 项」是这一页最有说服力的东西，一旦
     变成手填就会和清单不一致 —— 而且没人会去核对。所以要断言「页面上的数字 ==
     实际公开记录里该等级的条数」。
  2. **按年分组不能重复或漏年**。分组是在 Python 里切段的（依赖 Meta.ordering
     已经排好），排序一变就会出现「2025 出现两次」这种事。
  3. **证书条带只有真的有照片时才出现**。一排空占位框摆在这一页顶部，等于把
     「我们连证书都没拍」放在最显眼的位置。
  4. **站务必须能录入**。站务是等级 4、没有 `is_staff`，打不开 Django Admin，
     而录奖恰好是站务在做的事 —— 所以驾驶舱那一页是刚需，不是锦上添花。

跑法：python scripts/check_honors.py
"""
import atexit
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

from shoot import PORT, DevServer, do_login  # noqa: E402

SHOTS = REPO / ".shots"
SEED_TAG = "自动化荣誉"
failures = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


WALL = """
() => {
    const num = (sel) => {
        const el = document.querySelector(sel + ' strong');
        return el ? parseInt(el.textContent.trim(), 10) : null;
    };
    const years = [...document.querySelectorAll('.hn-year-no')].map(e => e.textContent.trim());
    return {
        national: num('.hn-stat.hn-lv-national'),
        provincial: num('.hn-stat.hn-lv-provincial'),
        school: num('.hn-stat.hn-lv-school'),
        heroTotal: (document.querySelector('.page-hero-sub strong') || {}).textContent || '',
        years: years,
        rows: document.querySelectorAll('.hn-row').length,
        titles: [...document.querySelectorAll('.hn-title')].map(e => e.textContent.trim()),
        // 每一年分组里有几行
        perYear: [...document.querySelectorAll('.hn-year')].map(
            y => y.querySelectorAll('.hn-row').length),
        certs: document.querySelectorAll('.hn-cert').length,
        certStrip: !!document.querySelector('.hn-cert-strip'),
        links: [...document.querySelectorAll('.hn-row.is-link')].map(a => a.getAttribute('href')),
        badges: [...document.querySelectorAll('.hn-row .hn-badge')].map(e => e.textContent.trim()),
        empty: !!document.querySelector('.empty-state'),
        emptyText: (document.querySelector('.empty-state') || {}).textContent || '',
    };
}
"""

HOME = """
() => {
    const sec = document.getElementById('nf-honors');
    if (!sec) return { present: false };
    return {
        present: true,
        rows: sec.querySelectorAll('.hn-row').length,
        titles: [...sec.querySelectorAll('.hn-title')].map(e => e.textContent.trim()),
        // 首页不分组，所以每行都要带年份
        yearTags: sec.querySelectorAll('.hn-year-tag').length,
        moreHref: (sec.querySelector('.nf-link-more') || {}).getAttribute
            ? sec.querySelector('.nf-link-more').getAttribute('href') : null,
    };
}
"""


def png(color=(201, 138, 61), size=(600, 450)):
    from io import BytesIO

    from django.core.files.base import ContentFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return ContentFile(buf.getvalue(), name="cert.png")


def hide_real_honors():
    """把**不属于本脚本**的公开荣誉临时收起来，返回它们的 pk 以便还原。

    为什么需要这一步：下面的断言是「墙上有几条」「按年怎么分组」「一条都没有时
    空态什么样」—— 库里有真实获奖记录时它们全部对不上（`import_honors` 导入 15 条
    之后就是这样）。而真实记录不能删，那是站上的正式数据。

    所以只能临时把 `is_public` 关掉：`Honor.wall()` 和首页那一段都按它过滤，
    关掉就等于从墙上拿下来，而记录本身一个字没动。收尾必须还原 —— 见
    `restore_real_honors()`，它挂在 atexit 上，崩在中间也会跑。
    """
    from news.models import Honor

    pks = list(
        Honor.objects.filter(is_public=True)
        .exclude(title__startswith=SEED_TAG)
        .values_list("pk", flat=True)
    )
    if pks:
        Honor.objects.filter(pk__in=pks).update(is_public=False)
    return pks


def restore_real_honors(pks):
    from news.models import Honor

    if pks:
        Honor.objects.filter(pk__in=pks).update(is_public=True)
        print(f"（已把 {len(pks)} 条真实荣誉放回墙上）")


def wipe():
    from news.models import Honor, Post

    for h in Honor.objects.filter(title__startswith=SEED_TAG):
        if h.certificate:
            h.certificate.delete(save=False)
        h.delete()
    Post.objects.filter(title__startswith=SEED_TAG).delete()


def seed():
    """建 6 条记录：三个等级、三个年份、一条不公开、一条带证书、一条关联喜报。"""
    from news.models import Honor, Post

    wipe()
    story = Post.objects.create(
        title=f"{SEED_TAG}·电赛国一喜报", category=Post.Category.HONOR,
        body="队伍拿下了全国一等奖。", is_published=True,
    )
    made = {}
    made["national"] = Honor.objects.create(
        title=f"{SEED_TAG}·全国大学生电子设计竞赛 一等奖", contest="电赛",
        level=Honor.Level.NATIONAL, year=2025, awardee="张三、李四、王五",
        is_public=True, is_featured=True, post=story, certificate=png(),
    )
    made["provincial"] = Honor.objects.create(
        title=f"{SEED_TAG}·省级智能车竞赛 二等奖", contest="智能车",
        level=Honor.Level.PROVINCIAL, year=2025, awardee="赵六",
        is_public=True, is_featured=True,
    )
    made["school"] = Honor.objects.create(
        title=f"{SEED_TAG}·校级科技创新大赛 三等奖",
        level=Honor.Level.SCHOOL, year=2024, awardee="孙七",
        is_public=True,
    )
    made["school2"] = Honor.objects.create(
        title=f"{SEED_TAG}·校级程序设计竞赛 优胜奖",
        level=Honor.Level.SCHOOL, year=2024,
        is_public=True,
    )
    made["old"] = Honor.objects.create(
        title=f"{SEED_TAG}·早年的一个奖",
        level=Honor.Level.OTHER, year=2019,
        is_public=True,
    )
    # 不公开：荣誉墙与统计都不该算它
    made["hidden"] = Honor.objects.create(
        title=f"{SEED_TAG}·还没核实的奖",
        level=Honor.Level.NATIONAL, year=2026,
        is_public=False, note="内部待核实",
    )
    return {k: v.pk for k, v in made.items()}, story.pk


def expected_counts():
    from news.models import Honor

    return Honor.summary()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    import django

    SHOTS.mkdir(exist_ok=True)
    django.setup()

    import dev_account

    user, password = dev_account.ensure(level=4)

    # 先把真实荣誉从墙上临时拿下来，再造样例 —— 顺序不能反：`seed()` 里的
    # `wipe()` 只清本脚本自己的记录，而下面的计数断言要求墙上只有样例。
    #
    # **用 atexit 而不是 try/finally**：还原必须在任何退出路径上都发生（断言失败
    # 提前 return、Playwright 抛异常、Ctrl+C），而给这个 450 行的函数整体套一层
    # try 要把里面全部重新缩进 —— 那种改动最容易在别处出错。
    hidden = hide_real_honors()
    if hidden:
        print(f"（把 {len(hidden)} 条真实荣誉临时收起来，跑完还原）")
    atexit.register(restore_real_honors, hidden)

    ids, story_pk = seed()
    want = expected_counts()
    print(f"已建 6 条记录（1 条不公开）；公开统计：国 {want['national']} 省 {want['provincial']} 校 {want['school']}")

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        base = f"http://127.0.0.1:{PORT}"
        vp = {"width": 1440, "height": 1000}
        errors, failed = [], []

        def watch(page):
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("requestfailed", lambda r: failed.append(r.url))
            page.on("response",
                    lambda r: failed.append(f"{r.url} HTTP {r.status}") if r.status >= 400 else None)

        # ---------------- 荣誉墙 ----------------
        print("\n荣誉墙：统计必须是数出来的")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        watch(page)
        page.goto(base + "/honors/", wait_until="load")
        page.wait_for_timeout(500)
        st = page.evaluate(WALL)

        check(st["national"] == want["national"],
              "国家级计数和实际公开记录一致",
              f"页面 {st['national']} / 实际 {want['national']}")
        check(st["provincial"] == want["provincial"],
              "省级计数一致", f"页面 {st['provincial']} / 实际 {want['provincial']}")
        check(st["school"] == want["school"],
              "校级计数一致", f"页面 {st['school']} / 实际 {want['school']}")
        check(st["heroTotal"].strip() == str(want["total"]),
              "总数一致", f"页面 {st['heroTotal'].strip()} / 实际 {want['total']}")
        check(st["rows"] == want["total"],
              "清单行数 = 公开记录数", f"{st['rows']} 行 / {want['total']} 条")

        # 不公开的那条一点痕迹都不能留
        check(not any("还没核实" in t for t in st["titles"]),
              "不公开的记录没出现在墙上")
        body = page.evaluate("() => document.body.textContent")
        check("内部待核实" not in body, "不公开记录的备注也没泄漏")

        # 分组
        check(st["years"] == ["2025", "2024", "2019"],
              "按年降序分组，不重复不漏", str(st["years"]))
        check(len(st["years"]) == len(set(st["years"])), "同一年只出现一个分组")
        check(sum(st["perYear"]) == st["rows"], "每行都落在某个年份分组里",
              f"分组内共 {sum(st['perYear'])} 行 / 总 {st['rows']} 行")
        check(st["perYear"] == [2, 2, 1], "各年条数正确", str(st["perYear"]))

        # 同年内按含金量降序
        check(st["badges"][:2] == ["国家级", "省级"],
              "同一年里国家级排在省级前面", str(st["badges"][:2]))

        # 等级色只染徽章，不染奖项名。踩过：`.hn-lv-national strong` 同时命中了
        # 行里的 strong.hn-title，整份清单按等级染成四色，读起来像彩虹。
        colors = page.evaluate("""() => {
            const titles = [...document.querySelectorAll('.hn-row .hn-title')]
                .map(e => getComputedStyle(e).color);
            const badges = [...document.querySelectorAll('.hn-row .hn-badge')]
                .map(e => getComputedStyle(e).color);
            return { titles: [...new Set(titles)], badges: [...new Set(badges)] };
        }""")
        check(len(colors["titles"]) == 1,
              "奖项名一律同一个颜色（等级色不染标题）", str(colors["titles"]))
        check(len(colors["badges"]) >= 3,
              "徽章按等级分色", f"{len(colors['badges'])} 种颜色")

        # 证书条带
        check(st["certStrip"] and st["certs"] == 1,
              "证书条带只放真的有照片的那一条", f"{st['certs']} 张")
        # 证书图必须按 4:3 裁，不能按原图高度铺开。踩过：模板给 <img> 写了
        # width/height 属性（防 CLS），宽高都确定时 CSS 的 aspect-ratio 会被忽略，
        # 一张 600x450 的图渲染成 235x450，一张就占掉半屏。
        box = page.evaluate("""() => {
            const i = document.querySelector('.hn-cert img');
            const r = i.getBoundingClientRect();
            return { w: Math.round(r.width), h: Math.round(r.height) };
        }""")
        check(abs(box["w"] / box["h"] - 4 / 3) < 0.05,
              "证书图按 4:3 裁（aspect-ratio 真的生效）",
              f"{box['w']}x{box['h']} = {box['w'] / box['h']:.2f}")

        # 关联喜报的那条是链接，没关联的不是
        check(len(st["links"]) == 1 and f"/news/{story_pk}/" in st["links"][0],
              "有喜报的那条是链接，指向那篇公告", str(st["links"]))
        page.screenshot(path=str(SHOTS / "honors-wall.png"))
        ctx.close()

        # ---------------- 首页分镜 08 ----------------
        print("\n首页分镜 08：只出首页展示的那几条")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        watch(page)
        page.goto(base + "/", wait_until="load")
        page.wait_for_timeout(1200)
        h = page.evaluate(HOME)
        check(h["present"], "有首页荣誉时分镜 08 出现")
        check(h["rows"] == 2, "只列勾了首页展示的两条", f"{h['rows']} 条")
        check(not any("校级" in t for t in h["titles"]),
              "没勾首页的公开记录不上首页", str(h["titles"]))
        check(h["yearTags"] == h["rows"],
              "首页每行都带年份（不分组，年份必须在行里）",
              f"{h['yearTags']} 个年份标签 / {h['rows']} 行")
        check(h["moreHref"] == "/honors/", "「看全部荣誉」指向荣誉墙", str(h["moreHref"]))

        # 「累计 N 项」那行不能和标题叠字。踩过：给它加了 margin-top:-18px 往上贴，
        # 直接被拉进 h2 的行盒里叠在「拿过的奖」上面。结构断言看不出这种事。
        lay = page.evaluate("""() => {
            const sec = document.getElementById('nf-honors');
            const h2 = sec.querySelector('.nf-display');
            const sub = sec.querySelector('.nf-honors-sub');
            if (!sub) return null;
            return {
                h2Bottom: Math.round(h2.getBoundingClientRect().bottom),
                subTop: Math.round(sub.getBoundingClientRect().top),
            };
        }""")
        check(lay and lay["subTop"] >= lay["h2Bottom"] - 2,
              "副标题在标题下方，不叠字",
              f"标题底 {lay['h2Bottom']} / 副标题顶 {lay['subTop']}")
        check(not errors, "无未捕获异常", "; ".join(errors[:2]))
        check(not failed, "无失败请求", "; ".join(failed[:3]))
        ctx.close()

        # ---------------- 撤回公开要连带撤掉首页 ----------------
        print("\n撤回公开时必须连带撤掉首页展示")
        ctx = browser.new_context(viewport=vp)
        do_login(ctx, base, f"{user}:{password}")
        page = ctx.new_page()
        page.goto(base + "/dashboard/honors/", wait_until="load")
        page.wait_for_timeout(400)
        rows = page.eval_on_selector_all("tbody tr", "els => els.length")
        check(rows >= 6, "驾驶舱列出了全部记录（含不公开的）", f"{rows} 行")

        # 找到那条既公开又在首页的，点「撤回」
        page.evaluate("""() => {
            const rows = [...document.querySelectorAll('tbody tr')];
            const row = rows.find(r => r.textContent.includes('全国大学生电子设计竞赛'));
            const form = [...row.querySelectorAll('form')].find(
                f => f.querySelector('[name=action]').value === 'toggle_public');
            form.querySelector('button').click();
        }""")
        page.wait_for_load_state("load")
        page.wait_for_timeout(500)
        from news.models import Honor

        h1 = Honor.objects.get(pk=ids["national"])
        check(not h1.is_public, "已撤回公开")
        check(not h1.is_featured,
              "首页展示被连带撤掉（否则首页会指向一条已经不公开的记录）")
        page.screenshot(path=str(SHOTS / "honors-dashboard.png"))
        ctx.close()

        # 撤回后首页与墙都应少一条
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        page.goto(base + "/honors/", wait_until="load")
        page.wait_for_timeout(400)
        st = page.evaluate(WALL)
        check(not any("全国大学生电子设计竞赛" in t for t in st["titles"]),
              "撤回后墙上也没有了")
        check(not st["certStrip"], "唯一的证书随之撤回，证书条带整段消失")
        ctx.close()

        # ---------------- 站务能录入（等级 4 打不开 Django Admin） ----------------
        print("\n站务录入（等级 4 没有 is_staff，Django Admin 进不去）")
        ctx = browser.new_context(viewport=vp)
        do_login(ctx, base, f"{user}:{password}")
        page = ctx.new_page()
        resp = page.goto(base + "/admin/", wait_until="load")
        check(resp.status in (200, 302) and "/admin/login" in page.url or "login" in page.url,
              "站务确实进不了 Django Admin（被挡在登录页）", page.url)

        page.goto(base + "/dashboard/honors/", wait_until="load")
        page.wait_for_timeout(400)
        page.fill("#id_title", f"{SEED_TAG}·站务录入的奖")
        page.fill("#id_year", "2023")
        page.select_option("#id_level", str(int(Honor.Level.PROVINCIAL)))
        # 用 data-honor-save 而不是 button[type=submit]：这一页每行都有三个小表单，
        # 各带一个提交按钮，靠「第一个匹配」定位会随 DOM 顺序点错东西。
        with page.expect_navigation(wait_until="load"):
            page.click("[data-honor-save]")
        page.wait_for_timeout(400)
        created = Honor.objects.filter(title__endswith="站务录入的奖").first()
        check(created is not None, "站务成功录入一条",
              "" if created else f"停在 {page.url}；页面提示："
              + " ".join(page.eval_on_selector_all(
                  ".form-error, .alert", "els => els.map(e => e.textContent.trim())")[:3]))
        check(created and created.is_public and created.year == 2023,
              "字段都存对了", f"{getattr(created, 'year', '?')} / 公开={getattr(created, 'is_public', '?')}")

        # 年份打错一位必须被拦（否则荣誉墙多出一个荒诞的年份分组）
        page.goto(base + "/dashboard/honors/", wait_until="load")
        page.wait_for_timeout(300)
        page.fill("#id_title", f"{SEED_TAG}·年份打错")
        page.fill("#id_year", "205")
        with page.expect_navigation(wait_until="load"):
            page.click("[data-honor-save]")
        page.wait_for_timeout(400)
        check(not Honor.objects.filter(title__endswith="年份打错").exists(),
              "年份 205 被拦下（不会多出一个荒诞的年份分组）")
        errs = page.eval_on_selector_all(".form-error", "els => els.length")
        check(errs > 0, "并且给出了错误提示", f"{errs} 条")
        ctx.close()

        # ---------------- 移动端 ----------------
        print("\n移动端（年份从左侧一列变成上方一行）")
        ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                  is_mobile=True, has_touch=True, device_scale_factor=2)
        page = ctx.new_page()
        merrs = []
        page.on("pageerror", lambda e: merrs.append(str(e)))
        page.goto(base + "/honors/", wait_until="load")
        page.wait_for_timeout(600)
        m = page.evaluate("""() => {
            const y = document.querySelector('.hn-year');
            const row = document.querySelector('.hn-row');
            const no = document.querySelector('.hn-year-no');
            return {
                vw: window.innerWidth,
                docW: document.documentElement.scrollWidth,
                cols: getComputedStyle(y).gridTemplateColumns,
                noPos: getComputedStyle(no).position,
                rowW: row ? Math.round(row.getBoundingClientRect().width) : 0,
                heroTop: Math.round(document.querySelector('.page-hero h1').getBoundingClientRect().top),
                navBottom: Math.round(document.querySelector('.site-nav').getBoundingClientRect().bottom),
            };
        }""")
        check(m["docW"] <= m["vw"] + 1, "没有横向溢出",
              f"文档宽 {m['docW']} / 视口 {m['vw']}")
        check(len(m["cols"].split()) == 1,
              "年份不再占一列（换成上方一行）", m["cols"])
        check(m["noPos"] == "static", "年份不再 sticky", m["noPos"])
        check(m["rowW"] > m["vw"] * 0.8, "行占满宽度", f"{m['rowW']}")
        check(m["heroTop"] >= m["navBottom"], "标题没被固定导航切掉",
              f"{m['heroTop']} / {m['navBottom']}")
        check(not merrs, "移动端无未捕获异常", "; ".join(merrs[:2]))
        page.screenshot(path=str(SHOTS / "honors-mobile.png"), full_page=True)
        ctx.close()

        # ---------------- 空态 ----------------
        print("\n一条公开记录都没有时的空态")
        wipe()
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        page.goto(base + "/honors/", wait_until="load")
        page.wait_for_timeout(400)
        st = page.evaluate(WALL)
        check(st["empty"], "渲染了设计过的空态（不是一片空白）")
        check("公告" in st["emptyText"], "空态给出了下一步")
        check(not st["certStrip"], "空态不显示证书条带")
        page.screenshot(path=str(SHOTS / "honors-empty.png"))

        page.goto(base + "/", wait_until="load")
        page.wait_for_timeout(900)
        h = page.evaluate(HOME)
        check(not h["present"], "首页分镜 08 整段不渲染")
        ctx.close()

        browser.close()

    # --keep：保留造出来的数据，方便接着用 shoot.py 肉眼看。默认清掉，
    # 否则开发库里会堆一堆「自动化荣誉·」。
    if "--keep" in sys.argv:
        seed()
        print("\n（--keep）已重新造好样例数据，可以直接 shoot.py --url /honors/ 看")
    else:
        wipe()
    dev_account.ensure(level=4)

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("荣誉墙契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
