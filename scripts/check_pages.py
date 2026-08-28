# -*- coding: utf-8 -*-
"""校验 Tier 2 内容页的统一升级：导航、共用件（页头/卡片/药丸/分页/空态）。

Task 18 把八组内容页收敛到一套共用件上，所以这个脚本守的是**收敛本身**，而不是
某一页好不好看：

  1. **导航条目数量是个硬约束。** 改版前顶层平铺 10 条，实测「会标 + 链接 + 右侧」
     只剩 10px 余量，用户名长一点就把链接挤到换行（「新生指 南」裂成两行），而
     汉堡菜单要到 720px 才接手 —— 721~1090px 这一整段宽度里导航是坏的。所以要
     在多个宽度上断言「要么单行不溢出，要么已经收进汉堡」。
  2. **翻页不能把筛选条件丢掉。** 原来 11 个模板各自手拼 `?page=N&...`，抄漏一个
     参数就是「翻到第二页筛选没了」，页面照常渲染、没有任何报错。现在统一走
     `includes/pager.html` + `{% querystring %}`，这条要端到端验。
  3. **切筛选要把 page 清掉。** 否则在第 3 页换个分类，落到一个空列表上。
  4. **空态必须给下一步。** 「暂无内容」是死胡同。
  5. **`projects/detail.html` 曾经引用只存在于 dashboard.css 的类**，而那一页不
     加载它 —— 表格不能横向滚动、行内按钮不排、空态是裸文本，而控制台干净。

跑法：python scripts/check_pages.py [--keep]
"""
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
TAG = "自动化页面"
failures = []

# 每一页：路径、页头强调色是否自定义、eyebrow 文案
LIST_PAGES = [
    ("/news/", "// NEWS"),
    ("/events/", "// EVENTS"),
    ("/resources/", "// RESOURCES"),
    ("/works/", "// OUR WORK"),
    ("/honors/", "// HONORS"),
    ("/team/", "// THE TEAM"),
    ("/points/leaderboard/", "// LEADERBOARD"),
]


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


NAV = """
() => {
    const links = document.getElementById('nav-links');
    const brand = document.querySelector('.nav-brand');
    const auth = document.querySelector('.nav-auth');
    const burger = document.getElementById('nav-burger');
    const w = e => Math.round(e.getBoundingClientRect().width);
    const top = [...links.children].filter(e => e.tagName === 'A' || e.tagName === 'DETAILS');
    return {
        vw: window.innerWidth,
        burgerShown: getComputedStyle(burger).display !== 'none',
        linksShown: getComputedStyle(links).display !== 'none',
        topCount: top.length,
        // 单行的判据：链接区高度不超过一个条目的高度（换行会翻倍）
        linksH: Math.round(links.getBoundingClientRect().height),
        itemH: top.length ? Math.round(top[0].getBoundingClientRect().height) : 0,
        need: Math.round(w(brand) + links.scrollWidth + w(auth) + 60),
        avail: Math.round(document.querySelector('.nav-inner').getBoundingClientRect().width),
        docW: document.documentElement.scrollWidth,
        groups: document.querySelectorAll('[data-nav-group]').length,
        openGroups: document.querySelectorAll('[data-nav-group][open]').length,
        wallLinks: ['/works/', '/honors/', '/team/']
            .map(h => !!links.querySelector('a[href="' + h + '"]')),
    };
}
"""

PAGE = """
() => {
    const hero = document.querySelector('.page-hero');
    const grid = hero ? getComputedStyle(hero, '::before') : null;
    const cards = [...document.querySelectorAll('.card')];
    const box = e => {
        const s = getComputedStyle(e);
        return s.borderRadius + '|' + s.borderTopWidth + '|' + s.backgroundColor;
    };
    return {
        hero: !!hero,
        heroScope: hero ? hero.classList.contains('nf-scope') : false,
        heroGrid: hero ? getComputedStyle(hero).backgroundColor : '',
        eyebrow: (document.querySelector('.page-hero .nf-eyebrow') || {}).textContent || '',
        accent: (() => {
            const a = document.querySelector('.page-hero h1 .accent');
            return a ? getComputedStyle(a).color : '';
        })(),
        heroTop: hero ? Math.round(hero.querySelector('h1').getBoundingClientRect().top) : 0,
        navBottom: Math.round(document.querySelector('.site-nav').getBoundingClientRect().bottom),
        cards: cards.length,
        cardBoxes: [...new Set(cards.map(box))],
        pills: document.querySelectorAll('.pill').length,
        currentPills: document.querySelectorAll('.pill.is-current').length,
        pager: !!document.querySelector('nav.pagination[aria-label]'),
        pagerLinks: [...document.querySelectorAll('.pagination a')].map(a => a.getAttribute('href')),
        empty: !!document.querySelector('.empty-state'),
        emptyHasNext: !!document.querySelector('.empty-state a'),
        emptyText: (document.querySelector('.empty-state') || {}).textContent || '',
        docW: document.documentElement.scrollWidth,
        vw: window.innerWidth,
        // 旧类名一处都不该剩
        legacy: ['empty-hint', 'filter-tabs', 'wk-hero', 'hn-hero', 'tm-hero',
                 'dash-table-wrap', 'dash-row-actions', 'dash-empty']
            .filter(c => document.querySelector('.' + c)),
    };
}
"""


def wipe():
    from django.contrib.auth import get_user_model

    from events.models import Event
    from news.models import Post
    from notify.models import Notification
    from points.models import PointLog

    Post.objects.filter(title__startswith=TAG).delete()
    Event.objects.filter(title__startswith=TAG).delete()
    Notification.objects.filter(title__startswith=TAG).delete()
    PointLog.objects.filter(note__startswith=TAG).delete()
    get_user_model().objects.filter(username="pagebot").delete()


def seed():
    """造够翻页的量：15 篇公告（跨两个分类）+ 3 场活动 + 通知 + 积分明细。"""
    import datetime

    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from accounts import roles
    from events.models import Event
    from news.models import Post
    from notify.models import Notification
    from points.models import PointLog

    User = get_user_model()
    wipe()

    author = User.objects.filter(is_superuser=True).first() or User.objects.first()

    now = timezone.now()
    # **同一个分类里要够翻页**（每页 12）：核心契约是「筛选之后翻页，筛选还在」，
    # 如果筛完只剩一页，分页控件压根不渲染，那条断言就变成了空跑。
    for i in range(15):
        Post.objects.create(
            title=f"{TAG}·通知 {i + 1:02d}",
            category=Post.Category.NOTICE,
            body=f"第 {i + 1} 条自动化公告正文。",
            is_published=True,
            published_at=now - datetime.timedelta(days=i),
            author=author,
        )
    for i in range(3):
        Post.objects.create(
            title=f"{TAG}·动态 {i + 1}",
            category=Post.Category.ACTIVITY,
            body="自动化协会动态正文。",
            is_published=True,
            published_at=now - datetime.timedelta(days=20 + i),
            author=author,
        )
    for i in range(3):
        Event.objects.create(
            title=f"{TAG}·活动 {i + 1}",
            description="自动化活动说明。",
            location="启航活动中心 21B",
            start_at=now + datetime.timedelta(days=i + 1),
            end_at=now + datetime.timedelta(days=i + 1, hours=2),
            points_reward=5,
            is_published=True,
            created_by=author,
        )

    bot = User.objects.create_user(username="pagebot", password="pagebot-dev-only")
    bot.real_name = "自动化页面账号"
    bot.college = "集成电路学院"
    bot.grade = "2025"
    bot.save()
    bot.set_level(roles.LEVEL_FORMAL)
    # set_level 会写一条等级变更通知，这里再补几条好看分页
    for i in range(3):
        Notification.objects.create(
            user=bot, title=f"{TAG}·通知 {i + 1}", body="自动化通知正文。",
            kind=Notification.Kind.SYSTEM,
        )
    for i in range(4):
        PointLog.objects.create(
            user=bot, delta=5 if i % 2 else -2, source=PointLog.Source.EVENT_CHECKIN,
            note=f"{TAG}·积分 {i + 1}",
        )
    return bot.username, "pagebot-dev-only"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    import django

    SHOTS.mkdir(exist_ok=True)
    django.setup()

    import dev_account

    officer, officer_pw = dev_account.ensure(level=4)
    bot, bot_pw = seed()
    print(f"已造 15 篇公告 / 3 场活动 / 通知与积分明细；成员账号 {bot}")

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

        # ---------------- 导航：宽度与溢出 ----------------
        print("\n导航：任何宽度下要么单行不溢出，要么已经收进汉堡")
        for width in (1440, 1280, 1100, 1025, 1024, 900, 390):
            ctx = browser.new_context(viewport={"width": width, "height": 900})
            page = ctx.new_page()
            page.goto(base + "/news/", wait_until="load")
            page.wait_for_timeout(250)
            n = page.evaluate(NAV)
            if n["burgerShown"]:
                check(not n["linksShown"], f"{width}px 汉堡接手，桌面导航已收起")
            else:
                single = n["linksH"] <= n["itemH"] + 2
                check(single and n["need"] <= n["avail"],
                      f"{width}px 导航单行且不溢出",
                      f"高 {n['linksH']}/{n['itemH']} · 需 {n['need']} / 可用 {n['avail']}")
            check(n["docW"] <= n["vw"] + 1, f"{width}px 无横向溢出",
                  f"{n['docW']} / {n['vw']}")
            ctx.close()

        # ---------------- 导航：折叠组 ----------------
        print("\n导航折叠组（了解协会 / 学习资源）")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        watch(page)
        page.goto(base + "/news/", wait_until="load")
        page.wait_for_timeout(400)
        n = page.evaluate(NAV)
        check(n["groups"] == 2, "两个折叠组", f"{n['groups']} 个")
        check(n["openGroups"] == 0, "默认全部收起")
        check(n["topCount"] <= 6, "顶层条目不超过 6 个（原来平铺 10 个挤到换行）",
              f"{n['topCount']} 个")
        check(all(n["wallLinks"]),
              "作品墙 / 荣誉墙 / 团队都进了导航（Task 15/16/17 推迟过来的）",
              str(n["wallLinks"]))

        # 点开第一组
        page.click("[data-nav-group] > summary")
        page.wait_for_timeout(250)
        vis = page.evaluate("""() => {
            const m = document.querySelector('[data-nav-group][open] .nav-group-menu');
            if (!m) return null;
            const r = m.getBoundingClientRect();
            return { w: Math.round(r.width), h: Math.round(r.height),
                     pos: getComputedStyle(m).position,
                     items: m.querySelectorAll('a').length };
        }""")
        check(vis and vis["h"] > 100 and vis["pos"] == "absolute",
              "点开后浮层菜单真的显示出来", str(vis))
        check(vis and vis["items"] == 5, "第一组 5 个条目", str(vis and vis["items"]))

        # 点开第二组，第一组要自动关
        page.click("[data-nav-group]:nth-of-type(2) > summary")
        page.wait_for_timeout(250)
        n = page.evaluate(NAV)
        check(n["openGroups"] == 1, "同时只开一个折叠组", f"{n['openGroups']} 个开着")

        # Esc 关闭并把焦点还给 summary
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        after = page.evaluate("""() => ({
            open: document.querySelectorAll('[data-nav-group][open]').length,
            focused: document.activeElement.tagName,
        })""")
        check(after["open"] == 0, "按 Esc 关闭")
        check(after["focused"] == "SUMMARY",
              "焦点还给触发它的 summary（否则键盘用户要从头 Tab 一遍）",
              after["focused"])

        # 点外面关闭
        page.click("[data-nav-group] > summary")
        page.wait_for_timeout(150)
        page.click(".page-hero h1")
        page.wait_for_timeout(200)
        check(page.evaluate("() => document.querySelectorAll('[data-nav-group][open]').length") == 0,
              "点菜单外面关闭")
        ctx.close()

        # 无 JS 时折叠组仍然能展开（原生 <details>）
        print("\nsite.js 加载失败：折叠组必须还能展开")
        ctx = browser.new_context(viewport=vp)
        ctx.route("**/js/site*.js", lambda route: route.fulfill(status=404, body=""))
        page = ctx.new_page()
        page.goto(base + "/news/", wait_until="load")
        page.wait_for_timeout(400)
        page.click("[data-nav-group] > summary")
        page.wait_for_timeout(200)
        check(page.evaluate("() => document.querySelectorAll('[data-nav-group][open]').length") == 1,
              "没有 JS 也能展开（原生 details，不是靠脚本加类）")
        check(page.evaluate(
            """() => !!document.querySelector('[data-nav-group][open] a[href="/works/"]')"""),
            "菜单里的链接可达")
        ctx.close()

        # ---------------- 共用件：每一页都吃到 ----------------
        print("\n共用页头横幅：七个列表页都吃到，且各自的强调色不同")
        accents = {}
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        watch(page)
        for path, eyebrow in LIST_PAGES:
            page.goto(base + path, wait_until="load")
            page.wait_for_timeout(300)
            st = page.evaluate(PAGE)
            check(st["hero"] and st["heroScope"],
                  f"{path} 有页头横幅且叠了示波器网格")
            check(st["eyebrow"].strip() == eyebrow, f"{path} eyebrow 正确",
                  st["eyebrow"].strip())
            check(st["heroTop"] >= st["navBottom"],
                  f"{path} 标题没被固定导航切掉",
                  f"{st['heroTop']} / {st['navBottom']}")
            check(not st["legacy"], f"{path} 没有残留的旧类名", str(st["legacy"]))
            if st["accent"]:
                accents[path] = st["accent"]
        check(len(set(accents.values())) >= 3,
              "各页强调色确实不同（--hero-accent 生效）", str(sorted(set(accents.values()))))

        print("\n卡片统一：同一页里所有 .card 的描边 / 圆角 / 底色一致")
        for path in ("/news/", "/events/", "/points/leaderboard/"):
            page.goto(base + path, wait_until="load")
            page.wait_for_timeout(300)
            st = page.evaluate(PAGE)
            if st["cards"]:
                check(len(st["cardBoxes"]) == 1,
                      f"{path} 卡片盒子样式只有一种", f"{st['cards']} 张 / {st['cardBoxes']}")
        ctx.close()

        # ---------------- 分页要带着筛选走 ----------------
        print("\n分页：翻页不能把筛选条件丢掉（原来 11 处各自手拼 querystring）")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        watch(page)
        page.goto(base + "/news/", wait_until="load")
        page.wait_for_timeout(300)
        st = page.evaluate(PAGE)
        check(st["pager"], "分页控件带 nav[aria-label]（无障碍语义）")
        check(len(st["pagerLinks"]) >= 1, "有翻页链接", str(st["pagerLinks"]))

        # 先筛分类，再翻页，分类必须还在。刻意挑「通知公告」——种子数据在这个分类
        # 里放了 15 条（每页 12），筛完仍有两页；筛完只剩一页的话分页控件压根不
        # 渲染，下面那条核心断言就变成了空跑。
        page.click('.pill[href*="category=notice"]')
        page.wait_for_load_state("load")
        page.wait_for_timeout(300)
        url_filtered = page.url
        check("category=notice" in url_filtered, "筛选进了 URL", url_filtered)
        cur = page.evaluate("() => document.querySelector('.pill.is-current').textContent.trim()")

        nxt = page.evaluate(
            """() => { const a = [...document.querySelectorAll('.pagination a')]
                 .find(x => x.getAttribute('rel') === 'next');
                 return a ? a.getAttribute('href') : null; }""")
        check(nxt and "category=" in nxt,
              "「下一页」的链接里仍然带着分类（这条是本任务的核心回归）", str(nxt))
        if nxt:
            page.click('.pagination a[rel="next"]')
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)
            st2 = page.evaluate(PAGE)
            after_cur = page.evaluate(
                "() => document.querySelector('.pill.is-current').textContent.trim()")
            check(after_cur == cur, "翻页之后筛选仍然高亮在同一个分类",
                  f"{cur} → {after_cur}")
            check("category=" in page.url and "page=2" in page.url,
                  "URL 同时带着分类与页码", page.url)
            check(st2["cards"] > 0, "第二页真的有内容", f"{st2['cards']} 张")

            # 在第 2 页切筛选，page 必须被清掉
            page.click('.pill:not(.is-current)')
            page.wait_for_load_state("load")
            page.wait_for_timeout(300)
            check("page=" not in page.url,
                  "在第 2 页切换筛选时 page 被清掉（否则落到一个空列表上）", page.url)
        check(not errors, "无未捕获异常", "; ".join(errors[:2]))
        check(not failed, "无失败请求", "; ".join(failed[:3]))
        page.screenshot(path=str(SHOTS / "pages-news.png"), full_page=True)
        ctx.close()

        # ---------------- 空态一律给下一步 ----------------
        print("\n空态：统一成 .empty-state，且必须给下一步")
        empties = [
            ("/news/?category=honor", "公告（没有喜报分类的帖子）"),
            ("/events/?tab=past", "活动（往期）"),
            ("/resources/?q=zzzz-no-such-thing", "资料站（搜不到）"),
        ]
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        for path, label in empties:
            page.goto(base + path, wait_until="load")
            page.wait_for_timeout(250)
            st = page.evaluate(PAGE)
            check(st["empty"], f"{label} 渲染了设计过的空态")
            check(st["emptyHasNext"], f"{label} 空态给了下一步（不是死胡同）")
            check(st["cards"] == 0, f"{label} 没有空壳卡片")
        ctx.close()

        # ---------------- 会员页 ----------------
        print("\n会员页（通知 / 积分 / 项目档案库 / 个人中心）")
        ctx = browser.new_context(viewport=vp)
        do_login(ctx, base, f"{bot}:{bot_pw}")
        page = ctx.new_page()
        watch(page)
        for path, eyebrow in (("/notify/", "// NOTIFICATIONS"),
                              ("/points/", "// POINTS"),
                              ("/projects/", "// PROJECTS")):
            page.goto(base + path, wait_until="load")
            page.wait_for_timeout(300)
            st = page.evaluate(PAGE)
            check(st["hero"] and st["heroScope"], f"{path} 有页头横幅")
            check(st["eyebrow"].strip() == eyebrow, f"{path} eyebrow 正确", st["eyebrow"].strip())
            check(not st["legacy"], f"{path} 没有残留的旧类名", str(st["legacy"]))

        page.goto(base + "/accounts/profile/", wait_until="load")
        page.wait_for_timeout(300)
        prof = page.evaluate("""() => ({
            insetEmpties: document.querySelectorAll('.inset-empty').length,
            legacy: document.querySelectorAll('.empty-hint').length,
        })""")
        check(prof["legacy"] == 0, "个人中心不再用 .empty-hint")
        check(prof["insetEmpties"] >= 1,
              "面板里的小空态走 .inset-empty（比整页空态轻一档）",
              f"{prof['insetEmpties']} 处")
        check(not errors, "会员页无未捕获异常", "; ".join(errors[:2]))
        check(not failed, "会员页无失败请求", "; ".join(failed[:3]))
        ctx.close()

        # ---------------- 项目档案库：修掉的真 bug ----------------
        print("\n项目档案库详情页：原来引用了只存在于 dashboard.css 的类")
        from projects.models import Project, ProjectMember
        from django.contrib.auth import get_user_model

        User = get_user_model()
        bot_user = User.objects.get(username=bot)
        proj = Project.objects.filter(name__startswith=TAG).first()
        if not proj:
            proj = Project.objects.create(
                name=f"{TAG}·项目", summary="自动化项目简介。",
                created_by=bot_user,
            )
        ProjectMember.objects.get_or_create(project=proj, user=bot_user,
                                            defaults={"role": "lead"})
        ctx = browser.new_context(viewport=vp)
        do_login(ctx, base, f"{bot}:{bot_pw}")
        page = ctx.new_page()
        watch(page)
        page.goto(base + f"/projects/{proj.pk}/", wait_until="load")
        page.wait_for_timeout(300)
        det = page.evaluate("""() => {
            const wrap = document.querySelector('.table-wrap');
            const empty = document.querySelector('.inset-empty');
            return {
                legacy: ['dash-table-wrap', 'dash-row-actions', 'dash-empty']
                    .filter(c => document.querySelector('.' + c)),
                overflowX: wrap ? getComputedStyle(wrap).overflowX : '',
                emptyCentered: empty ? getComputedStyle(empty).textAlign : '',
                inlineStyles: document.querySelectorAll('.proj-main [style]').length,
            };
        }""")
        check(not det["legacy"], "不再引用 dashboard.css 的类", str(det["legacy"]))
        check(det["overflowX"] == "auto",
              "文件表格真的能横向滚动了（原来那个类没有样式）", det["overflowX"])
        check(det["emptyCentered"] == "center",
              "目录空态有样式了（原来是一行裸文本）", det["emptyCentered"])
        page.screenshot(path=str(SHOTS / "pages-project.png"), full_page=True)
        ctx.close()

        # ---------------- 移动端 ----------------
        print("\n移动端（汉堡菜单里折叠组就地展开）")
        ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                  is_mobile=True, has_touch=True, device_scale_factor=2)
        page = ctx.new_page()
        merrs = []
        page.on("pageerror", lambda e: merrs.append(str(e)))
        page.goto(base + "/news/", wait_until="load")
        page.wait_for_timeout(500)
        page.click("#nav-burger")
        page.wait_for_timeout(300)
        m = page.evaluate("""() => {
            const links = document.getElementById('nav-links');
            return {
                open: document.getElementById('site-nav').classList.contains('nav-open'),
                linksVisible: getComputedStyle(links).display !== 'none',
                expanded: document.getElementById('nav-burger').getAttribute('aria-expanded'),
            };
        }""")
        check(m["open"] and m["linksVisible"], "汉堡展开后导航可见")
        check(m["expanded"] == "true", "aria-expanded 同步了")

        page.click("[data-nav-group] > summary")
        page.wait_for_timeout(300)
        mm = page.evaluate("""() => {
            const menu = document.querySelector('[data-nav-group][open] .nav-group-menu');
            return {
                pos: menu ? getComputedStyle(menu).position : '',
                docW: document.documentElement.scrollWidth,
                vw: window.innerWidth,
            };
        }""")
        check(mm["pos"] == "static",
              "窄屏折叠组就地展开成缩进清单（浮层会盖住自己的触发器）", mm["pos"])
        check(mm["docW"] <= mm["vw"] + 1, "展开后仍无横向溢出",
              f"{mm['docW']} / {mm['vw']}")
        page.screenshot(path=str(SHOTS / "pages-mobile-nav.png"))

        # 点面板外面要收起来（触屏上没有别的关法）。
        # 不能用 `page.click(选择器)` —— 展开的面板盖在页面内容上，Playwright 会一直
        # 报「被 .nav-auth 拦住」然后超时。也不能写死一个 y 坐标：折叠组展开后面板
        # 高度会变。现场量一下面板底边，点它下面 20px。
        nav_bottom = page.evaluate(
            "() => Math.round(document.querySelector('.site-nav').getBoundingClientRect().bottom)")
        check(nav_bottom + 20 < 844, "面板没有占满整屏（还点得到外面）", f"底边 {nav_bottom}")
        page.mouse.click(195, nav_bottom + 20)
        page.wait_for_timeout(300)
        check(not page.evaluate(
            "() => document.getElementById('site-nav').classList.contains('nav-open')"),
            "点面板外面收起汉堡")

        for path in ("/news/", "/events/", "/resources/", "/points/leaderboard/"):
            page.goto(base + path, wait_until="load")
            page.wait_for_timeout(400)
            st = page.evaluate(PAGE)
            check(st["docW"] <= st["vw"] + 1, f"移动端 {path} 无横向溢出",
                  f"{st['docW']} / {st['vw']}")
            check(st["heroTop"] >= st["navBottom"], f"移动端 {path} 标题没被导航切掉",
                  f"{st['heroTop']} / {st['navBottom']}")
        check(not merrs, "移动端无未捕获异常", "; ".join(merrs[:2]))
        page.screenshot(path=str(SHOTS / "pages-mobile-news.png"), full_page=True)
        ctx.close()

        browser.close()

    if "--keep" in sys.argv:
        seed()
        print("\n（--keep）已重新造好样例数据")
    else:
        from projects.models import Project

        Project.objects.filter(name__startswith=TAG).delete()
        wipe()
    dev_account.ensure(level=4)

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("内容页统一升级契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
