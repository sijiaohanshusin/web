# -*- coding: utf-8 -*-
"""校验无障碍契约：键盘走得通、读屏读得对、对比度够。

这一类问题几乎不会自己暴露：鼠标能点、页面能看、控制台干净，所有既有检查脚本
一路绿灯。真实踩到过的一条就在这里被钉住 —— **消息提示整条被固定导航盖住**：
「保存成功」「验证码已发送」的文字确实在 DOM 里，于是按 textContent 断言的脚本
（check_register / check_media_center）都通过了，而屏幕上那一块是空的。

所以这里的判据一律是「**渲染之后到底能不能用**」：
  - 位置：提示的顶边在导航底边之下，且 `elementFromPoint` 命中的是它自己
  - 键盘：Tab 一次就能拿到跳转链接，回车之后焦点真的落进 <main>
  - 焦点环：拿到键盘焦点时 outline 宽度真的大于 0
  - 对比度：从渲染出来的 color 和**逐层向上找到的**不透明背景现算比值

对比度那一节刻意跳过「背景是渐变或图片」的元素：那种情况下算不出唯一的背景色，
硬算出来的数字比不算更糟（会给出一个看着精确、其实无意义的结论）。跳过的会打印
出来，不会假装检查过。

跑法：python scripts/check_a11y.py [--keep]
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

import dev_account  # noqa: E402
from shoot import PORT, DevServer  # noqa: E402

SHOTS = REPO / ".shots"
failures = []
notes = []

# 全站扫一遍的页面。挑的是「读者真的会走到」的那几条路，而不是全部 URL。
SWEEP = [
    ("/", "首页"),
    ("/news/", "公告列表"),
    ("/recruit/", "新生指南"),
    ("/works/", "作品墙"),
    ("/honors/", "荣誉墙"),
    ("/team/", "团队页"),
    ("/recruitment/", "招新落地页"),
    ("/accounts/register/", "注册选通道"),
    ("/accounts/login/", "登录"),
]


TAG = "自动化无障碍"


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


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


def seed():
    """一件带封面的作品 + 一篇带封面的公告。

    为什么非要种：`alt` 那条断言在页面上一张图都没有时是**空跑**的。而现在协会
    素材还没补齐，作品墙 / 公告列表 / 团队页现实里都是零张图 —— 断言全绿而什么
    都没查。数据库驱动的图恰好也是最容易漏 alt 的一类（模板写 `alt="{{ ... }}"`，
    值是空的时候就渲染成 `alt=""`），所以这两页必须真的有图。
    """
    from io import BytesIO

    from django.contrib.auth import get_user_model
    from django.core.files.base import ContentFile
    from django.utils import timezone
    from PIL import Image

    from news.models import Post
    from projects.models import Project

    def png(color):
        buf = BytesIO()
        Image.new("RGB", (800, 600), color).save(buf, format="PNG")
        return ContentFile(buf.getvalue(), name="cover.png")

    wipe()
    author = get_user_model().objects.filter(is_superuser=True).first() \
        or get_user_model().objects.first()
    Project.objects.create(
        name=f"{TAG}·带封面的作品",
        summary="自动化：这一件用来让作品墙上真的有一张图可查 alt。",
        highlight="一句话亮点。",
        department=Project.Department.HARDWARE,
        is_public=True, created_by=author, cover=png((41, 216, 232)),
    )
    Post.objects.create(
        title=f"{TAG}·带封面的公告",
        category=Post.Category.NOTICE,
        body="自动化正文。",
        is_published=True, published_at=timezone.now(),
        author=author, cover=png((13, 169, 205)),
    )


def login_code(email: str) -> str:
    """现发一条登录验证码并把明文取回来。

    走的是服务端真正在用的 `verification.issue`，不是自己往表里塞一行 —— 那样
    绕过了有效期与 purpose 校验，测出来的就不是真流程了。dev 的邮件后端不外发。
    """
    from accounts import verification

    return verification.issue(email, "login").code


# ---------------------------------------------------------------- 页面级扫描
PAGE_AUDIT = """
() => {
    const out = {};
    out.lang = document.documentElement.getAttribute('lang') || '';

    // 地标
    out.mains = document.querySelectorAll('main').length;
    out.mainId = (document.querySelector('main') || {}).id || '';
    out.navsUnnamed = [...document.querySelectorAll('nav')]
        .filter(n => !n.getAttribute('aria-label') && !n.getAttribute('aria-labelledby')).length;

    // 标题层级：只看真的渲染出来的（display:none 的不算）
    const heads = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')]
        .filter(h => h.offsetParent !== null || h.getClientRects().length);
    out.h1 = heads.filter(h => h.tagName === 'H1').length;
    out.levels = heads.map(h => +h.tagName[1]);
    out.skips = [];
    for (let i = 1; i < out.levels.length; i++) {
        if (out.levels[i] - out.levels[i - 1] > 1) {
            out.skips.push(`h${out.levels[i - 1]}→h${out.levels[i]}「`
                + heads[i].textContent.trim().slice(0, 14) + '」');
        }
    }

    // 图片 alt：属性缺失才算问题，alt="" 是「装饰性」的正确写法
    const imgs = [...document.querySelectorAll('img')];
    out.imgs = imgs.length;
    out.imgNoAlt = imgs.filter(i => !i.hasAttribute('alt'))
        .map(i => (i.getAttribute('src') || '').split('/').pop()).slice(0, 6);

    // 正的 tabindex 会把元素抽到所有自然顺序之前，键盘顺序就乱了
    out.positiveTabindex = [...document.querySelectorAll('[tabindex]')]
        .filter(e => +e.getAttribute('tabindex') > 0)
        .map(e => e.tagName + '.' + e.className).slice(0, 5);

    // 跳转链接
    const skip = document.querySelector('a.skip-link');
    out.hasSkip = !!skip;
    out.skipTargetExists = skip ? !!document.querySelector(skip.getAttribute('href')) : false;
    // 没聚焦时必须不占版面（否则鼠标用户会看到一条莫名的链接）
    if (skip) {
        const r = skip.getBoundingClientRect();
        out.skipIdleBox = [Math.round(r.width), Math.round(r.height)];
    }
    return out;
}
"""

# ---------------------------------------------------------------- 对比度
# 取一批代表性的文字角色，每种取第一个实例。逐层向上找不透明背景色；
# 中途碰到 background-image（渐变、示波器网格、照片）就放弃这个元素。
CONTRAST = """
(targets) => {
    const parse = (c) => {
        const m = c.match(/rgba?\\(([^)]+)\\)/);
        if (!m) return null;
        const p = m[1].split(',').map(s => parseFloat(s));
        return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
    };
    const lin = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    const lum = (c) => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
    const ratio = (a, b) => {
        const [hi, lo] = lum(a) >= lum(b) ? [lum(a), lum(b)] : [lum(b), lum(a)];
        return (hi + 0.05) / (lo + 0.05);
    };

    const rows = [];
    for (const t of targets) {
        // 目标可以是 "选择器"，也可以是 ["选择器", "rgb(...)"] —— 后者用于背景是
        // 渐变/底纹、算不出唯一背景色的场合：**把那一层底下的平底色显式写出来**，
        // 于是这一格从「跳过」变成真的断言。白区的坐标纸底纹就是这种情况：
        // 网格线极淡，有效背景就是 --paper。
        const sel = Array.isArray(t) ? t[0] : t;
        const assumed = Array.isArray(t) ? t[1] : null;
        const el = document.querySelector(sel);
        if (!el) { rows.push({ sel, state: 'absent' }); continue; }
        if (!(el.offsetParent !== null || el.getClientRects().length)) {
            rows.push({ sel, state: 'hidden' }); continue;
        }
        const cs = getComputedStyle(el);
        const fg = parse(cs.color);
        // 大字（>=24px，或 >=18.66px 且加粗）走 AA 的 3:1 门槛
        const size = parseFloat(cs.fontSize);
        const bold = (parseInt(cs.fontWeight, 10) || 400) >= 700;
        const large = size >= 24 || (size >= 18.66 && bold);

        // 逐层向上找背景。半透明的那几层**能算准**：把它们按顺序叠到下面第一个
        // 不透明色上就是真实背景色（卡片的 rgba(255,255,255,.022) 叠在纯黑上就是
        // #0a0a0b）。所以不跳过它们 —— 跳过的话像 .card 里的所有文字都测不到。
        // 真正算不准的只有 background-image（渐变、示波器网格、照片）：那时背景
        // 逐像素都不一样，硬给一个数字比不给更糟。
        let node = el, base = null, painted = false;
        const layers = [];
        while (node && node.nodeType === 1) {
            const s = getComputedStyle(node);
            if (s.backgroundImage && s.backgroundImage !== 'none') { painted = true; break; }
            const c = parse(s.backgroundColor);
            if (c && c.a >= 1) { base = c; break; }
            if (c && c.a > 0) layers.push(c);
            node = node.parentElement;
        }
        if (assumed) { base = parse(assumed); painted = false; layers.length = 0; }
        if (painted || !base || !fg) {
            rows.push({ sel, state: 'skip',
                        why: painted ? '背景是图/渐变' : '找不到不透明背景' });
            continue;
        }
        // 从最下面那层往上叠
        let bg = base;
        for (let i = layers.length - 1; i >= 0; i--) {
            const t = layers[i];
            bg = { r: t.r * t.a + bg.r * (1 - t.a),
                   g: t.g * t.a + bg.g * (1 - t.a),
                   b: t.b * t.a + bg.b * (1 - t.a), a: 1 };
        }
        bg = { r: Math.round(bg.r), g: Math.round(bg.g), b: Math.round(bg.b), a: 1 };
        rows.push({
            sel, state: 'ok', ratio: +ratio(fg, bg).toFixed(2),
            need: large ? 3 : 4.5, large,
            fg: cs.color, bg: `rgb(${bg.r}, ${bg.g}, ${bg.b})`,
            size: Math.round(size),
        });
    }
    return rows;
}
"""

# 每种文字角色一个代表。挑的都是「读者真的要读」的正文与标签，
# 不含纯装饰（丝印记号、aria-hidden 的时钟）。
CONTRAST_TARGETS = {
    "/": [
        ".nf-hero-title", ".nf-hero-sub", ".site-footer p",
        ".footer-col a", ".footer-bar span",
        # 白区那几条的背景是坐标纸底纹（background-image），逐层向上找不到平底色。
        # 网格线极淡，有效背景就是 --paper #f7f8fa —— 显式写出来让它真的被量。
        # 不写的话这几条会被跳过，而白区上的强调色恰好是全站唯一不达标的地方。
        [".nf-light p", "rgb(247, 248, 250)"],
        [".nf-light .nf-eyebrow", "rgb(247, 248, 250)"],
        [".nf-light .nf-display .accent", "rgb(247, 248, 250)"],
        [".nf-light h3", "rgb(247, 248, 250)"],
        ".nf-dir-body p",
    ],
    "/news/": [
        # 页头横幅叠着示波器网格，平底色是 --black。
        # 现在还多叠了一张氛围图（`--scope-art`），但**这个假设仍然成立** ——
        # 图的意象被要求只放在右 40%，标题与导语在左 55% 的纯黑区里，
        # 而 `check_artwork.py` 断言那一区的 99 分位亮度 ≤30。
        [".page-hero h1", "rgb(5, 5, 6)"], [".page-hero-sub", "rgb(5, 5, 6)"],
        ".news-card-title", ".news-card-meta", ".pill", ".footer-col a",
    ],
    # `.recruit-content h2` 现在压在章节头横幅（背景图）上，会被这段逻辑正确地
    # 跳过 —— 图背景算不出唯一底色。所以另外补两个**实底**角色进来，否则这一页
    # 只剩 2 个可量元素，会触发下面「至少量到 3 个」那条守卫。
    # 横幅上的白字改由 `check_artwork.py` 保证：它断言横幅左侧（标题区）的
    # 99 分位亮度 ≤80，白字压上去仍在 9:1 以上。
    "/recruit/": [
        ".recruit-content p", ".recruit-content h2", ".rg-meta", ".recruit-toc a",
        ".recruit-content h3", ".recruit-content .sec-sub",
    ],
}


def sweep(page, base, url, name):
    page.goto(base + url, wait_until="load")
    # 首页有开场遮罩，量之前先等它撤掉（锁期间 body 变滚动容器、几何都是中间态）
    page.wait_for_function(
        "() => !document.documentElement.classList.contains('esta-pre-lock')", timeout=20000)
    page.wait_for_timeout(500)
    a = page.evaluate(PAGE_AUDIT)
    print(f"\n{name}  {url}")
    check(a["lang"].startswith("zh"), f"{name} <html lang> 是中文", a["lang"] or "(空)")
    check(a["mains"] == 1, f"{name} 正好一个 <main>", f"{a['mains']} 个")
    check(a["mainId"] == "main", f"{name} <main> 带 id（跳转链接的落点）", a["mainId"] or "(无)")
    check(a["navsUnnamed"] == 0, f"{name} 每个 <nav> 都有名字", f"{a['navsUnnamed']} 个没名字")
    check(a["h1"] == 1, f"{name} 正好一个 h1", f"{a['h1']} 个")
    check(not a["skips"], f"{name} 标题层级不跳级", "; ".join(a["skips"][:3]))
    # 图片数只做记录，不做断言：素材还没补齐，好几页现在一张图都没有是正常状态。
    # 「alt 那条别空跑」由收尾处的全局计数守（见 total_imgs）。
    print(f"       {a['imgs']} 张图")
    check(not a["imgNoAlt"], f"{name} 每张图都有 alt 属性", ", ".join(a["imgNoAlt"]))
    check(not a["positiveTabindex"], f"{name} 没有正的 tabindex",
          ", ".join(a["positiveTabindex"]))
    check(a["hasSkip"] and a["skipTargetExists"], f"{name} 有跳转链接且落点存在")
    if a.get("skipIdleBox"):
        w, h = a["skipIdleBox"]
        check(w <= 2 and h <= 2, f"{name} 跳转链接平时不占版面", f"{w}x{h}")
    return a


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    import django

    SHOTS.mkdir(exist_ok=True)
    django.setup()
    dev_account.ensure(level=4)
    seed()
    print(f"已种 1 件带封面作品 + 1 篇带封面公告（前缀「{TAG}」）")

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        base = f"http://127.0.0.1:{PORT}"
        vp = {"width": 1440, "height": 1000}
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        # ---------------- 页面级扫描 ----------------
        print("逐页扫描：lang / 地标 / 标题层级 / alt / tabindex / 跳转链接")
        total_imgs = 0
        seen = {}
        for url, name in SWEEP:
            a = sweep(page, base, url, name)
            total_imgs += a["imgs"]
            seen[url] = a["imgs"]
        print("\n「每张图都有 alt」这条不能空跑，所以数一遍到底查过多少张")
        check(total_imgs >= 60, "整轮一共查了足够多的图", f"{total_imgs} 张")
        # 这两页的图是本脚本自己种下的数据库图（模板侧 alt 由 Django 测试静态扫），
        # 数据库驱动的图才是真会漏 alt 的地方（MediaSlot.alt 站务不填就是空）
        check(seen.get("/works/", 0) >= 1, "作品墙上有种下的封面（数据库驱动的图）",
              f"{seen.get('/works/', 0)} 张")
        check(seen.get("/news/", 0) >= 1, "公告列表上有种下的封面",
              f"{seen.get('/news/', 0)} 张")

        # ---------------- 跳转链接端到端 ----------------
        print("\n「跳到主要内容」：Tab 一次拿到它，回车之后焦点真的落进 <main>")
        page.goto(base + "/news/", wait_until="load")
        page.wait_for_timeout(400)
        page.evaluate("() => document.body.focus()")
        page.keyboard.press("Tab")
        first = page.evaluate(
            """() => { const a = document.activeElement;
                       return { cls: a.className || '', tag: a.tagName,
                                text: (a.textContent || '').trim().slice(0, 12) }; }""")
        check("skip-link" in first["cls"],
              "**Tab 第一下就是跳转链接**（否则要穿过整排导航才能到正文）",
              f"{first['tag']}.{first['cls']} 「{first['text']}」")

        vis = page.evaluate(
            """() => { const s = document.querySelector('a.skip-link');
                const r = s.getBoundingClientRect();
                const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
                return { w: Math.round(r.width), h: Math.round(r.height),
                         inView: r.top >= 0 && r.left >= 0,
                         onTop: !!hit && (hit === s || s.contains(hit)) }; }""")
        check(vis["w"] > 40 and vis["h"] > 20, "聚焦后它真的显形了", f"{vis['w']}x{vis['h']}")
        check(vis["inView"], "显形的位置在视口里")
        check(vis["onTop"], "而且没有被固定导航盖住（elementFromPoint 命中它自己）")

        page.keyboard.press("Enter")
        page.wait_for_timeout(300)
        landed = page.evaluate(
            """() => { const a = document.activeElement;
                       return { tag: a.tagName, id: a.id || '',
                                inMain: !!a.closest('main') || a.tagName === 'MAIN' }; }""")
        check(landed["inMain"] or landed["id"] == "main",
              "**回车之后焦点落进了 <main>**（只滚动不移焦点的话，再按 Tab 又回到导航）",
              f"{landed['tag']}#{landed['id']}")

        # ---------------- 焦点环 ----------------
        print("\n键盘焦点环：拿到焦点时 outline 真的画出来了")
        ring = page.evaluate(
            """() => { const a = document.querySelector('.nav-links a');
                a.focus();
                const cs = getComputedStyle(a);
                return { w: parseFloat(cs.outlineWidth), style: cs.outlineStyle,
                         color: cs.outlineColor, matches: a.matches(':focus-visible') }; }""")
        check(ring["matches"], "编程式聚焦也算 :focus-visible（链接一律算）")
        check(ring["w"] >= 1.5 and ring["style"] != "none",
              "导航链接的焦点环有宽度", f"{ring['w']}px {ring['style']} {ring['color']}")

        # ---------------- 消息提示必须看得见（真实走一次登录） ----------------
        print("\n消息提示：走一次真实登录拿到「登录成功。」，看它到底在不在屏幕上")
        print("（这一条是真踩过的坑：文字在 DOM 里，所以按文本断言的脚本全绿）")
        # 刻意走**验证码登录**而不是密码登录：`accounts:login` 是 Django 自带的
        # LoginView，成功之后压根不发 message —— 拿它来验消息提示，`.alert` 永远
        # 不存在，这一整节会变成「找不到元素」而不是「提示被盖住」。
        # code_login 那一支自己写了 messages.success("登录成功。") 且认 ?next=。
        for nxt, where in [("/news/", "内页"), ("/", "首页")]:
            ctx.clear_cookies()   # LoginView 有 redirect_authenticated_user，得先退出来
            code = login_code(dev_account.EMAIL)
            page.goto(base + f"/accounts/login/code/?next={nxt}", wait_until="load")
            page.fill("#id_email", dev_account.EMAIL)
            page.fill("#id_code", code)
            with page.expect_navigation(wait_until="load"):
                page.click("form button[type=submit]")
            # 首页有开场遮罩，它会锁滚动；等它撤掉再量
            page.wait_for_function(
                "() => !document.documentElement.classList.contains('esta-pre-lock')",
                timeout=20000)
            page.wait_for_timeout(400)
            geo = page.evaluate(
                """() => { const al = document.querySelector('.alert');
                    if (!al) return { missing: true };
                    const w = document.querySelector('.messages-wrap');
                    const nav = document.querySelector('.site-nav').getBoundingClientRect();
                    const r = al.getBoundingClientRect();
                    const hit = document.elementFromPoint(r.left + r.width / 2,
                                                          r.top + r.height / 2);
                    return { text: al.textContent.trim().slice(0, 10),
                             top: Math.round(r.top), navBottom: Math.round(nav.bottom),
                             inMain: !!w.closest('main'),
                             role: w.getAttribute('role') || '',
                             onTop: !!hit && (hit === al || al.contains(hit)) }; }""")
            if geo.get("missing"):
                check(False, f"{where}登录后拿到了消息提示")
                continue
            check(True, f"{where}拿到了真实消息", geo["text"])
            check(geo["inMain"], f"{where}提示在 <main> 里（跳转落点之后就是它）")
            check(geo["role"] == "status", f"{where}提示区标了 role=status", geo["role"])
            check(geo["top"] >= geo["navBottom"],
                  f"**{where}提示的顶边在固定导航之下**（原来整条被盖住）",
                  f"提示顶 {geo['top']} / 导航底 {geo['navBottom']}")
            check(geo["onTop"], f"{where}提示中心点击得到（没有被别的层压着）")
            page.screenshot(path=str(SHOTS / f"a11y-message-{'home' if nxt == '/' else 'inner'}.png"),
                            clip={"x": 0, "y": 0, "width": 1440, "height": 320})
        # 退回未登录，别把开发库留在登录态影响别的脚本
        page.goto(base + "/", wait_until="load")
        ctx.clear_cookies()

        # ---------------- 播放按钮是真按钮 ----------------
        print("\n招新视频：入口必须是那颗真按钮，不是外层 div")
        page.goto(base + "/", wait_until="load")
        page.wait_for_function(
            "() => !document.documentElement.classList.contains('esta-pre-lock')", timeout=20000)
        page.wait_for_timeout(300)
        btn = page.evaluate(
            """() => { const b = document.querySelector('[data-video-play]');
                return b ? { tag: b.tagName, type: b.getAttribute('type'),
                             label: b.getAttribute('aria-label') || '' } : null; }""")
        check(btn and btn["tag"] == "BUTTON", "是原生 <button>", str(btn and btn["tag"]))
        check(btn and btn["type"] == "button", "写了 type=button", str(btn and btn["type"]))
        check(bool(btn and btn["label"]), "有 aria-label", str(btn and btn["label"]))
        page.evaluate("""() => { const b = document.querySelector('[data-video-play]');
                                 b.scrollIntoView(); b.click(); }""")
        page.wait_for_timeout(400)
        played = page.evaluate(
            """() => { const f = document.querySelector('#video-facade iframe');
                       return { n: document.querySelectorAll('#video-facade iframe').length,
                                title: f ? f.getAttribute('title') || '' : '' }; }""")
        check(played["n"] == 1, "点按钮真的装上了播放器，且只装一个", f"{played['n']} 个 iframe")
        check(bool(played["title"]), "iframe 有 title（读屏软件才知道这个框是什么）",
              played["title"])

        # ---------------- 筛选药丸的状态不能只靠颜色 ----------------
        print("\n筛选药丸：「现在筛的是哪一个」要能被读屏软件读出来")
        print("（.pill.is-current 改的只有三个颜色，不补 aria-current 的话十几个药丸听着一模一样）")
        for url, name in [("/news/", "公告"), ("/events/", "活动"), ("/works/", "作品墙")]:
            page.goto(base + url, wait_until="load")
            page.wait_for_timeout(400)
            st = page.evaluate(
                """() => {
                    const pills = [...document.querySelectorAll('.pill')];
                    const cur = pills.filter(p => p.classList.contains('is-current'));
                    return { total: pills.length, current: cur.length,
                             tagged: cur.filter(p => p.getAttribute('aria-current') === 'page').length,
                             strays: pills.filter(p => !p.classList.contains('is-current')
                                        && p.hasAttribute('aria-current')).length }; }""")
            check(st["total"] >= 2, f"{name} 页上真的有药丸可查", f"{st['total']} 个")
            check(st["current"] >= 1, f"{name} 页有一个处于当前态", f"{st['current']} 个")
            check(st["current"] == st["tagged"],
                  f"**{name} 页当前态的药丸都带 aria-current**",
                  f"{st['tagged']}/{st['current']}")
            check(st["strays"] == 0, f"{name} 页非当前态没有多余的 aria-current",
                  f"{st['strays']} 个")

        # ---------------- 对比度 ----------------
        print("\n对比度：从渲染出来的 color 与逐层向上找到的不透明背景现算")
        print("（背景是渐变/图片/半透明的会跳过并打印出来 —— 那种情况算不出唯一背景色）")
        for url, targets in CONTRAST_TARGETS.items():
            page.goto(base + url, wait_until="load")
            page.wait_for_function(
                "() => !document.documentElement.classList.contains('esta-pre-lock')",
                timeout=20000)
            page.wait_for_timeout(500)
            rows = page.evaluate(CONTRAST, targets)
            print(f"\n  {url}")
            measured = 0
            for r in rows:
                if r["state"] != "ok":
                    notes.append(f"{url} {r['sel']}：{r.get('why') or r['state']}")
                    print(f"    --   {r['sel']}  跳过（{r.get('why') or r['state']}）")
                    continue
                measured += 1
                ok = r["ratio"] >= r["need"]
                tag = "OK  " if ok else "FAIL"
                print(f"    {tag} {r['sel']}  {r['ratio']}:1"
                      f"（{r['size']}px 需要 {r['need']}:1）{r['fg']} on {r['bg']}")
                if not ok:
                    failures.append(f"对比度 {url} {r['sel']} = {r['ratio']}:1"
                                    f"（需要 {r['need']}:1）")
            check(measured >= 3, f"{url} 至少量到 3 个（不然这一节等于没跑）", f"{measured} 个")

        check(not errors, "整段无控制台报错", "; ".join(errors[:3]))
        ctx.close()

        # ---------------- 移动端：跳转链接同样可用 ----------------
        print("\n移动端：跳转链接与提示同样要能用")
        ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                  is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.goto(base + "/news/", wait_until="load")
        page.wait_for_timeout(400)
        page.evaluate("() => document.querySelector('a.skip-link').focus()")
        m = page.evaluate(
            """() => { const s = document.querySelector('a.skip-link');
                const r = s.getBoundingClientRect();
                return { w: Math.round(r.width), right: Math.round(r.right),
                         vw: window.innerWidth,
                         hit: (() => { const h = document.elementFromPoint(
                                r.left + r.width / 2, r.top + r.height / 2);
                                return !!h && (h === s || s.contains(h)); })() }; }""")
        check(m["right"] <= m["vw"], "窄屏上跳转链接不溢出", f"右缘 {m['right']} / 视口 {m['vw']}")
        check(m["hit"], "窄屏上它也在最上层")
        ctx.close()
        browser.close()

    dev_account.ensure(level=4)
    if "--keep" in sys.argv:
        print("\n（--keep）样例数据留着了。注意它是**公开**作品 + **已发布**公告，"
              "接着跑 check_works.py 之前先不带 --keep 跑一次清掉。")
    else:
        wipe()

    print()
    if notes:
        print(f"（对比度跳过 {len(notes)} 处，都是背景算不准的：不当作通过也不当作失败）")
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("无障碍契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
