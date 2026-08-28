# -*- coding: utf-8 -*-
"""校验跨页转场：命名元素真的配上了对，而不是各自淡入淡出。

这一项最容易「看着有动画，其实没配上」：如果两页的名字没对上，浏览器会让新元素
单独淡入 —— 屏幕上仍然有动静，肉眼多半看不出差别，但那个「图片长大了」的效果压根
没发生。所以判据不是「有没有动画」，而是**转场里同时存在 `::view-transition-old(名字)`
与 `::view-transition-new(名字)` 两个伪元素** —— 只有配上对时才会两个都在。

另外三件必须钉住的事：
  1. **同名元素在一页里必须唯一。** 列表页十几张卡片，全都命名会让浏览器直接跳过
     整个转场并在控制台报重名。所以名字只在导航那一刻给参与的那一张。
  2. **转场结束要把名字摘掉。** 留着的话下一次导航就重名，同样是静默跳过。
  3. **减动效偏好下一个名字都不许指派。**

做法：用 add_init_script 装一个记录器，它在每个文档里都先于页面脚本注册监听，把
观察结果写进 sessionStorage（导航会销毁 JS 上下文，只能靠 storage 跨页带过去）。
记录器刻意在 `requestAnimationFrame` 里读 DOM —— 它自己的监听器早于
view-transitions.js 执行，当场读的话名字还没指派上。

跑法：python scripts/check_transitions.py [--keep]
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

from shoot import PORT, DevServer  # noqa: E402

SHOTS = REPO / ".shots"
TAG = "自动化转场"
failures = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


# 每个文档都会先跑这一段（早于页面自己的脚本），所以监听器一定挂得上。
RECORDER = """
(() => {
    const KEY = '__vt_log';
    const push = (row) => {
        try {
            const log = JSON.parse(sessionStorage.getItem(KEY) || '[]');
            log.push(row);
            sessionStorage.setItem(KEY, JSON.stringify(log));
        } catch (e) { /* storage 满了也不能影响页面 */ }
    };
    const named = () => [...document.querySelectorAll('[data-vt-name]')]
        .map(el => el.getAttribute('data-vt-name'));

    window.addEventListener('pageswap', (e) => {
        // pageswap 之后这个文档就没了，没有 rAF 可用 —— 只记「有没有转场」和去向。
        push({ ev: 'swap', path: location.pathname, vt: !!e.viewTransition,
               to: (e.activation && e.activation.entry && e.activation.entry.url) || null });
    });

    window.addEventListener('pagereveal', (e) => {
        if (!e.viewTransition) {
            push({ ev: 'reveal', path: location.pathname, vt: false });
            return;
        }
        // **必须等一帧**：本监听器早于 view-transitions.js 执行，当场读 DOM
        // 名字还没指派；而伪元素动画要到转场真的开始才存在。
        requestAnimationFrame(() => {
            const pseudos = document.getAnimations()
                .map(a => a.effect && a.effect.pseudoElement)
                .filter(Boolean);
            push({ ev: 'reveal', path: location.pathname, vt: true,
                   named: named(), pseudos: pseudos });
        });
        // **收尾要等一个微任务之后再读。** 这个记录器由 add_init_script 装，
        // 注册 finished.then 早于 view-transitions.js，而 promise 回调按注册顺序
        // 跑 —— 当场读的话名字还没被摘掉，会把「已经摘干净」误判成残留。
        const after = (ev) => () => Promise.resolve().then(() =>
            push({ ev: ev, path: location.pathname, leftover: named() }));
        e.viewTransition.finished.then(after('finished'), after('aborted'));
    });
})();
"""

# 把转场冻在中途，好截一张能看的图。
# 为什么要冻：转场只有 .42s，而它是在新文档第一次渲染时才开始的 —— 「等 load 再等
# 160ms」是在和这个起点赛跑，`Page.captureScreenshot` 自己也要花时间，抓到的十次里
# 九次是已经落定的终态。看着像「压根没有转场」，其实是采样点不对。
# 代价是 `finished` 永远不 resolve，所以这一段单独开一个 context，不和断言混。
FREEZER = """
(() => {
    window.addEventListener('pagereveal', (e) => {
        if (!e.viewTransition) return;
        e.viewTransition.ready.then(() => {
            document.getAnimations()
                .filter(a => a.effect && a.effect.pseudoElement
                          && a.effect.pseudoElement.includes('view-transition'))
                .forEach(a => { a.pause(); a.currentTime = 170; });
            document.documentElement.dataset.vtFrozen = '1';
        }, () => {});
    });
})();
"""

READ_LOG = "() => JSON.parse(sessionStorage.getItem('__vt_log') || '[]')"
CLEAR_LOG = "() => sessionStorage.removeItem('__vt_log')"

STATIC_NAMES = """
() => {
    const name = (sel) => {
        const el = document.querySelector(sel);
        return el ? getComputedStyle(el).viewTransitionName : null;
    };
    return {
        nav: name('.site-nav'),
        hero: name('.page-hero') || name('.wk-detail-hero'),
        // 静止状态下不该有任何指派出来的名字
        assigned: document.querySelectorAll('[data-vt-name]').length,
        cards: document.querySelectorAll('a[data-vt-card]').length,
        parts: document.querySelectorAll('[data-vt-part]').length,
        ownParts: [...document.querySelectorAll('[data-vt-part]')]
            .filter(el => !el.closest('[data-vt-card]')).length,
    };
}
"""


def wipe():
    from news.models import Post
    from projects.models import Project

    for p in Project.objects.filter(name__startswith=TAG):
        if p.cover:
            p.cover.delete(save=False)
        p.delete()
    for p in Post.objects.filter(title__startswith=TAG):
        if p.cover:
            p.cover.delete(save=False)
        p.delete()


def png(color=(41, 216, 232), size=(800, 600)):
    from io import BytesIO

    from django.core.files.base import ContentFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return ContentFile(buf.getvalue(), name="cover.png")


def seed():
    """两件带封面的公开作品 + 两篇带封面的公告。

    要两件而不是一件：只有一张卡时「名字只给参与的那一张」这条根本没被考验到。
    """
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from news.models import Post
    from projects.models import Project

    User = get_user_model()
    wipe()
    author = User.objects.filter(is_superuser=True).first() or User.objects.first()

    works = []
    for i, color in enumerate([(41, 216, 232), (201, 138, 61)]):
        works.append(Project.objects.create(
            name=f"{TAG}·作品 {i + 1}",
            summary="自动化作品简介，用来验跨页转场。",
            highlight="一句话亮点。",
            department=Project.Department.HARDWARE,
            is_public=True,
            created_by=author,
            cover=png(color),
        ))
    posts = []
    for i in range(2):
        posts.append(Post.objects.create(
            title=f"{TAG}·公告 {i + 1}",
            category=Post.Category.NOTICE,
            body="自动化公告正文。",
            is_published=True,
            published_at=timezone.now(),
            author=author,
            cover=png((13, 169, 205)),
        ))
    return works, posts


def pairs_of(pseudos, name):
    """转场里这个名字有没有同时出现 old 与 new —— 配上对的唯一硬证据。"""
    has_old = any(f"::view-transition-old({name})" in p for p in pseudos)
    has_new = any(f"::view-transition-new({name})" in p for p in pseudos)
    return has_old, has_new


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    import django

    SHOTS.mkdir(exist_ok=True)
    django.setup()

    works, posts = seed()
    print(f"已造 2 件作品 + 2 篇公告（都带封面）；目标作品 pk={works[0].pk}")

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        base = f"http://127.0.0.1:{PORT}"
        vp = {"width": 1440, "height": 1000}

        # ---------------- 浏览器支持面 ----------------
        print("\n先确认这套 API 在当前浏览器里齐全（不齐全的话下面的断言没有意义）")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        page.goto(base + "/works/", wait_until="load")
        caps = page.evaluate("""() => ({
            swap: 'onpageswap' in window,
            reveal: 'onpagereveal' in window,
            navApi: typeof navigation === 'object',
            vtName: CSS.supports('view-transition-name', 'x'),
        })""")
        check(all(caps.values()), "pageswap / pagereveal / Navigation API / view-transition-name 都在",
              str(caps))
        ctx.close()

        # ---------------- 静止状态 ----------------
        print("\n静止状态：静态名字就位，指派出来的名字一个都不该有")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(base + "/works/", wait_until="load")
        page.wait_for_timeout(400)
        st = page.evaluate(STATIC_NAMES)
        check(st["nav"] == "site-nav", "固定导航条有静态名字（跨页保持钉住）", str(st["nav"]))
        check(st["hero"] == "page-hero", "页头横幅有静态名字", str(st["hero"]))
        check(st["cards"] >= 2, "作品墙上至少两张带标记的卡片", f"{st['cards']} 张")
        check(st["parts"] >= 2, "卡片封面都带 data-vt-part", f"{st['parts']} 个")
        check(st["ownParts"] == 0,
              "列表页没有「本页自己的」命名元素（全都在卡片里）", f"{st['ownParts']} 个")
        check(st["assigned"] == 0,
              "**静止时一个指派出来的名字都没有**（否则一页多张卡重名，转场会被整个跳过）",
              f"{st['assigned']} 个")

        detail = page.evaluate(
            """() => document.querySelector('a[data-vt-card][href]').getAttribute('href')""")
        page.goto(base + detail, wait_until="load")
        page.wait_for_timeout(400)
        sd = page.evaluate(STATIC_NAMES)
        check(sd["hero"] == "page-hero", "作品详情页的横幅也叫同一个名字（两边才能形变）",
              str(sd["hero"]))
        check(sd["ownParts"] == 1,
              "详情页正好一个「本页自己的」封面（底部推荐卡片不算）", f"{sd['ownParts']} 个")
        check(sd["assigned"] == 0, "详情页静止时也没有指派出来的名字", f"{sd['assigned']} 个")
        ctx.close()

        # ---------------- 列表 → 详情：封面必须配上对 ----------------
        print("\n作品墙 → 作品详情：封面要配上对（old 与 new 同时存在才算）")
        ctx = browser.new_context(viewport=vp)
        ctx.add_init_script(RECORDER)
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        page.goto(base + "/works/", wait_until="load")
        page.wait_for_timeout(500)
        page.evaluate(CLEAR_LOG)

        # 点第二张卡片：如果实现是「给第一张命名」这类偷懒写法，这一下就露馅
        href = page.evaluate(
            """() => [...document.querySelectorAll('a[data-vt-card][href]')]
                     .map(a => a.getAttribute('href'))[1]""")
        with page.expect_navigation(wait_until="load"):
            page.click(f'a[data-vt-card][href="{href}"]')
        page.wait_for_timeout(1000)

        log = page.evaluate(READ_LOG)
        swap = next((r for r in log if r["ev"] == "swap"), None)
        reveal = next((r for r in log if r["ev"] == "reveal" and r.get("vt")), None)
        done = next((r for r in log if r["ev"] in ("finished", "aborted")), None)

        check(swap and swap["vt"], "点内部链接触发了跨文档转场（pageswap 带 viewTransition）")
        check(swap and swap["to"] and href in swap["to"], "去向就是点的那张卡片",
              str(swap and swap["to"]))
        check(reveal is not None, "新页面的 pagereveal 也带 viewTransition")

        pseudos = (reveal or {}).get("pseudos") or []
        old_cover, new_cover = pairs_of(pseudos, "vt-cover")
        check(old_cover and new_cover,
              "**封面配上对了**（转场里 old 与 new 两个伪元素都在）",
              f"old={old_cover} new={new_cover}")
        old_hero, new_hero = pairs_of(pseudos, "page-hero")
        check(old_hero and new_hero, "页头横幅也配上对了", f"old={old_hero} new={new_hero}")
        old_nav, new_nav = pairs_of(pseudos, "site-nav")
        check(old_nav and new_nav, "固定导航条配上对（不跟着整页淡）",
              f"old={old_nav} new={new_nav}")
        check((reveal or {}).get("named") == ["cover"],
              "新页面上只指派了一个名字", str((reveal or {}).get("named")))
        check(done is not None and done["ev"] == "finished",
              "转场正常跑完（没有被中途放弃）", str(done and done["ev"]))
        check(done is not None and done.get("leftover") == [],
              "**转场结束把名字摘干净了**（留着会让下一次导航重名、整个转场被跳过）",
              str(done and done.get("leftover")))
        left = page.evaluate("() => document.querySelectorAll('[data-vt-name]').length")
        check(left == 0, "现场再确认一遍：页面上没有残留的指派名字", f"{left} 个")

        # ---------------- 连着跳第二次：残留会在这里现形 ----------------
        print("\n再从详情页点底部推荐卡片：第二次转场必须照样配上对")
        page.evaluate(CLEAR_LOG)
        more = page.evaluate(
            """() => { const a = document.querySelector('.wk-detail-more a[data-vt-card][href]')
                    || [...document.querySelectorAll('a[data-vt-card][href]')].pop();
                    return a ? a.getAttribute('href') : null; }""")
        if more:
            with page.expect_navigation(wait_until="load"):
                page.click(f'a[data-vt-card][href="{more}"]')
            page.wait_for_timeout(1000)
            log2 = page.evaluate(READ_LOG)
            reveal2 = next((r for r in log2 if r["ev"] == "reveal" and r.get("vt")), None)
            ps2 = (reveal2 or {}).get("pseudos") or []
            o2, n2 = pairs_of(ps2, "vt-cover")
            check(o2 and n2, "第二次转场封面照样配上对（说明上一次的名字确实摘掉了）",
                  f"old={o2} new={n2}")
        else:
            check(False, "详情页底部找得到推荐卡片")

        # ---------------- 后退回列表 ----------------
        print("\n浏览器后退回作品墙：名字要落在「来处那张卡片」上")
        page.evaluate(CLEAR_LOG)
        page.go_back(wait_until="load")
        page.wait_for_timeout(1000)
        log3 = page.evaluate(READ_LOG)
        reveal3 = next((r for r in log3 if r["ev"] == "reveal" and r.get("vt")), None)
        ps3 = (reveal3 or {}).get("pseudos") or []
        o3, n3 = pairs_of(ps3, "vt-cover")
        check(reveal3 is not None, "后退也走转场")
        check(o3 and n3, "后退时封面同样配上对（脚本按来处 URL 找回那张卡）",
              f"old={o3} new={n3}")
        check(not errors, "整段没有控制台报错（重名会在这里露头）", "; ".join(errors[:3]))
        ctx.close()

        # ---------------- 公告列表 → 公告详情 ----------------
        print("\n公告列表 → 公告详情：同一套标记，另一组模板")
        ctx = browser.new_context(viewport=vp)
        ctx.add_init_script(RECORDER)
        page = ctx.new_page()
        nerrs = []
        page.on("console", lambda m: nerrs.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: nerrs.append(str(e)))
        page.goto(base + "/news/", wait_until="load")
        page.wait_for_timeout(500)
        page.evaluate(CLEAR_LOG)
        nhref = page.evaluate(
            """() => { const a = document.querySelector('a[data-vt-card] [data-vt-part]');
                       return a ? a.closest('a[data-vt-card]').getAttribute('href') : null; }""")
        check(nhref is not None, "公告列表上有带封面的卡片", str(nhref))
        if nhref:
            with page.expect_navigation(wait_until="load"):
                page.click(f'a[data-vt-card][href="{nhref}"]')
            page.wait_for_timeout(1000)
            logn = page.evaluate(READ_LOG)
            rn = next((r for r in logn if r["ev"] == "reveal" and r.get("vt")), None)
            psn = (rn or {}).get("pseudos") or []
            on, nn = pairs_of(psn, "vt-cover")
            check(on and nn, "公告封面配上对", f"old={on} new={nn}")
            leftn = page.evaluate("() => document.querySelectorAll('[data-vt-name]').length")
            check(leftn == 0, "公告详情页也没有残留名字", f"{leftn} 个")
        check(not nerrs, "公告这一段无控制台报错", "; ".join(nerrs[:3]))
        ctx.close()

        # ---------------- 没有封面时不该硬配 ----------------
        print("\n没有封面的作品：不指派名字（占位框两边一样，morph 没有信息量）")
        from projects.models import Project

        bare = Project.objects.create(
            name=f"{TAG}·没有封面", summary="自动化：这件没有封面。",
            department=Project.Department.SOFTWARE, is_public=True,
            created_by=works[0].created_by,
        )
        ctx = browser.new_context(viewport=vp)
        ctx.add_init_script(RECORDER)
        page = ctx.new_page()
        page.goto(base + "/works/", wait_until="load")
        page.wait_for_timeout(400)
        page.evaluate(CLEAR_LOG)
        with page.expect_navigation(wait_until="load"):
            page.click(f'a[data-vt-card][href="/works/{bare.pk}/"]')
        page.wait_for_timeout(900)
        logb = page.evaluate(READ_LOG)
        rb = next((r for r in logb if r["ev"] == "reveal" and r.get("vt")), None)
        psb = (rb or {}).get("pseudos") or []
        ob, nb = pairs_of(psb, "vt-cover")
        check(not ob and not nb, "没有封面时压根没有 vt-cover 这一对",
              f"old={ob} new={nb}")
        oh, nh = pairs_of(psb, "page-hero")
        check(oh and nh, "但页头横幅照样形变（不因为缺图丢掉整段连续感）",
              f"old={oh} new={nh}")
        ctx.close()

        # ---------------- 减动效偏好 ----------------
        print("\nprefers-reduced-motion：一个名字都不许指派")
        ctx = browser.new_context(viewport=vp, reduced_motion="reduce")
        ctx.add_init_script(RECORDER)
        page = ctx.new_page()
        page.goto(base + "/works/", wait_until="load")
        page.wait_for_timeout(400)
        page.evaluate(CLEAR_LOG)
        with page.expect_navigation(wait_until="load"):
            page.click(f'a[data-vt-card][href="{href}"]')
        page.wait_for_timeout(900)
        logr = page.evaluate(READ_LOG)
        rr = next((r for r in logr if r["ev"] == "reveal" and r.get("vt")), None)
        assigned = (rr or {}).get("named") if rr else []
        check(not assigned, "减动效下没有指派任何名字", str(assigned))
        anim = page.evaluate("""() => document.getAnimations()
            .filter(a => a.effect && a.effect.pseudoElement
                      && a.effect.pseudoElement.includes('view-transition'))
            .length""")
        check(anim == 0, "减动效下页面上没有正在跑的转场动画", f"{anim} 个")
        page.screenshot(path=str(SHOTS / "transition-reduced.png"))
        ctx.close()

        # ---------------- 脚本加载失败 ----------------
        print("\nview-transitions.js 加载失败：跳转必须照常，只是没有连续感")
        ctx = browser.new_context(viewport=vp)
        ctx.route("**/js/view-transitions*.js", lambda r: r.fulfill(status=404, body=""))
        page = ctx.new_page()
        ferrs = []
        page.on("pageerror", lambda e: ferrs.append(str(e)))
        page.goto(base + "/works/", wait_until="load")
        page.wait_for_timeout(400)
        with page.expect_navigation(wait_until="load"):
            page.click(f'a[data-vt-card][href="{href}"]')
        page.wait_for_timeout(600)
        check(href in page.url, "照样跳到了详情页", page.url)
        check(page.evaluate(
            "() => !!document.querySelector('.wk-detail-hero')"), "详情页内容正常渲染")
        check(page.evaluate(
            "() => document.querySelectorAll('[data-vt-name]').length") == 0,
            "没有脚本时不会有任何指派名字")
        check(not ferrs, "没有未捕获异常", "; ".join(ferrs[:2]))
        ctx.close()

        # ---------------- 移动端 ----------------
        print("\n移动端：同一套逻辑，不降级")
        ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                  is_mobile=True, has_touch=True, device_scale_factor=2)
        ctx.add_init_script(RECORDER)
        page = ctx.new_page()
        merrs = []
        page.on("pageerror", lambda e: merrs.append(str(e)))
        page.goto(base + "/works/", wait_until="load")
        page.wait_for_timeout(600)
        page.evaluate(CLEAR_LOG)
        with page.expect_navigation(wait_until="load"):
            page.click(f'a[data-vt-card][href="{href}"]')
        page.wait_for_timeout(1000)
        logm = page.evaluate(READ_LOG)
        rm = next((r for r in logm if r["ev"] == "reveal" and r.get("vt")), None)
        psm = (rm or {}).get("pseudos") or []
        om, nm = pairs_of(psm, "vt-cover")
        check(om and nm, "移动端封面照样配上对", f"old={om} new={nm}")
        check(not merrs, "移动端无未捕获异常", "; ".join(merrs[:2]))
        ctx.close()

        # ---------------- 冻在中途截图，肉眼确认「图在长大」 ----------------
        print("\n把转场冻在 170ms 处截图（配上对与否肉眼可辨：图应该介于两个尺寸之间）")
        ctx = browser.new_context(viewport=vp)
        ctx.add_init_script(FREEZER)
        page = ctx.new_page()
        page.goto(base + "/works/", wait_until="load")
        page.wait_for_timeout(500)
        box = page.evaluate(
            """(h) => { const a = document.querySelector(`a[data-vt-card][href="${h}"]`);
                        const r = a.querySelector('[data-vt-part]').getBoundingClientRect();
                        return { w: Math.round(r.width), h: Math.round(r.height) }; }""",
            href)
        with page.expect_navigation(wait_until="load"):
            page.click(f'a[data-vt-card][href="{href}"]')
        page.wait_for_selector("html[data-vt-frozen]", timeout=5000)
        page.wait_for_timeout(120)
        page.screenshot(path=str(SHOTS / "transition-mid.png"))
        # 冻住的那一帧里，封面的实际取景框应该既不是卡片尺寸也不是详情页尺寸
        mid = page.evaluate(
            """() => { const g = document.getAnimations().find(
                   a => a.effect && a.effect.pseudoElement
                        && a.effect.pseudoElement === '::view-transition-group(vt-cover)');
                   if (!g) return null;
                   const s = getComputedStyle(document.documentElement,
                       '::view-transition-group(vt-cover)');
                   return { w: Math.round(parseFloat(s.width)),
                            h: Math.round(parseFloat(s.height)) }; }""")
        end = page.evaluate(
            """() => { const r = document.querySelector('[data-vt-part]')
                        .getBoundingClientRect();
                       return { w: Math.round(r.width), h: Math.round(r.height) }; }""")
        check(mid is not None, "冻住的那一帧里封面的组动画确实存在", str(mid))
        if mid:
            between = (min(box["w"], end["w"]) < mid["w"] < max(box["w"], end["w"])
                       or min(box["h"], end["h"]) < mid["h"] < max(box["h"], end["h"]))
            check(between,
                  "**中途那一帧的取景框介于卡片与详情页之间**（真在形变，不是整页闪一下）",
                  f"卡片 {box['w']}x{box['h']} → 中途 {mid['w']}x{mid['h']} → 详情 {end['w']}x{end['h']}")
        ctx.close()

        browser.close()

    if "--keep" in sys.argv:
        seed()
        print("\n（--keep）已重新造好样例数据，可以自己点进去看转场")
        print("  注意：留下的是**公开**作品与**已发布**公告，会出现在作品墙和公告列表上。"
              "\n  接着跑 check_works.py 之前先不带 --keep 跑一次把它们清掉 —— 那个脚本"
              "\n  按「墙上一共几件」断言，多出来的会让它红一片。")
    else:
        from projects.models import Project

        Project.objects.filter(name__startswith=TAG).delete()
        wipe()

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("跨页转场契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
