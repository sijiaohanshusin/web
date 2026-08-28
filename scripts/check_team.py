# -*- coding: utf-8 -*-
"""校验公开团队页：隐私边界、上墙口径、缺头像的样子、任命与同意两件事。

这一页和作品墙 / 荣誉墙的风险完全不同：**它列的是真人。**

  1. **隐私是硬约束，而且泄漏时页面看起来完全正常。** 注册时的同意书写的是
     「身份核验、招新联系、账号安全」，一个字都没提「公开展示在官网上」。所以
     上墙要本人单独勾选，而且页面上不能出现手机号 / 邮箱 / 学号 / QQ —— 这几样
     一旦被某个模板顺手带出去，没有任何报错，只有把页面源码整个搜一遍才发现。
  2. **任命 ≠ 上墙。** 站务在驾驶舱任命一个人，不等于替他同意公开自己的姓名和
     照片。所以驾驶舱那一页只显示「谁还没勾」，不提供代勾的开关；而且就算 POST
     里塞上这个字段也不能生效。
  3. **缺头像是常态，得有设计过的样子。** 协会现在几乎没人传头像，所以「没有
     头像」要渲染成丝印首字母牌，而不是一个碎图图标或者一块空白。
  4. **一个人都没勾时这一页也要站得住。** 聚合数字（在册人数等）不是个人信息，
     不受开关约束，是零 opt-in 时这一页的全部内容。

跑法：python scripts/check_team.py [--keep]
      --keep 保留造出来的样例数据，方便接着用 shoot.py 肉眼看
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
# 造出来的账号统一前缀，收尾按前缀删
SEED_USER = "teambot-"
SEED_POSITION = "自动化职位·硬件部长"
failures = []

# 这几个值只要出现在页面源码里就是泄漏。刻意选成不可能与别处文案碰撞的串。
SECRETS = {
    "phone": "13800997700",
    "email": "team-leak-probe@heuesta.invalid",
    "student_id": "2025770099",
    "qq": "877700991",
}


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


WALL = """
() => {
    const heroNums = [...document.querySelectorAll('.page-hero-sub strong')]
        .map(e => e.textContent.trim());
    return {
        names: [...document.querySelectorAll('.tm-name')].map(e => e.textContent.trim()),
        // 职位是卡片上的一枚徽章（不是分节标题）—— 顺序就是 sort_order 顺序
        posts: [...document.querySelectorAll('.tm-pos')].map(e => e.textContent.trim()),
        postColors: [...new Set([...document.querySelectorAll('.tm-pos')]
            .map(e => getComputedStyle(e).color))],
        edgeColors: [...new Set([...document.querySelectorAll('.tm-card')]
            .map(e => getComputedStyle(e).borderLeftColor))],
        // 名字一律中性色：职位色不能染到姓名上（一页五种颜色读成彩虹）
        nameColors: [...new Set([...document.querySelectorAll('.tm-name')]
            .map(e => getComputedStyle(e).color))],
        bios: [...document.querySelectorAll('.tm-bio')].map(e => e.textContent.trim()),
        roleBios: [...document.querySelectorAll('.tm-bio-role')].map(e => e.textContent.trim()),
        cohorts: [...document.querySelectorAll('.tm-cohort')].map(e => e.textContent.trim()),
        medals: [...document.querySelectorAll('.tm-medals li')].map(e => e.textContent.trim()),
        avatars: document.querySelectorAll('.tm-avatar').length,
        initials: [...document.querySelectorAll('.tm-initial')].map(e => e.textContent.trim()),
        heroNums: heroNums,
        heroText: (document.querySelector('.page-hero-sub') || {}).textContent || '',
        empty: !!document.querySelector('.empty-state'),
        emptyText: (document.querySelector('.empty-state') || {}).textContent || '',
        officerNote: !!document.querySelector('.tm-officer-note'),
        cards: document.querySelectorAll('.tm-card').length,
        cols: document.querySelector('.tm-grid')
            ? getComputedStyle(document.querySelector('.tm-grid'))
                .gridTemplateColumns.split(' ').length : 0,
    };
}
"""


def png(color=(41, 216, 232), size=(400, 400)):
    from io import BytesIO

    from django.core.files.base import ContentFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return ContentFile(buf.getvalue(), name="avatar.png")


def wipe():
    from django.contrib.auth import get_user_model

    from accounts.models import Medal, Position

    User = get_user_model()
    for user in User.objects.filter(username__startswith=SEED_USER):
        if user.avatar:
            user.avatar.delete(save=False)
        user.delete()
    Position.objects.filter(name=SEED_POSITION).delete()
    Medal.objects.filter(name__startswith="自动化勋章").delete()


def seed():
    """造 5 个人：
      · 主席，有头像、有介绍、有勋章 —— 完整的一张卡
      · 硬件主席，无头像 —— 验首字母牌
      · 软件主席，已任命但**没勾**公开展示 —— 不该上墙
      · 一个有职位但账号停用的 —— 不该上墙
      · 一个没职位的普通会员 —— 只进聚合数字，不上墙
    其中「主席」那位身上挂着全部四个敏感字段，用来验泄漏。
    """
    from django.contrib.auth import get_user_model

    from accounts import roles
    from accounts.models import Medal, Position, UserMedal

    User = get_user_model()
    wipe()

    chair = Position.objects.get(name="主席")
    hw = Position.objects.get(name="硬件主席")
    sw = Position.objects.get(name="软件主席")
    custom = Position.objects.create(
        name=SEED_POSITION, color="#41d8e8", blurb="带硬件方向的周常培训",
        sort_order=60, grants_management=False,
    )

    def mk(suffix, *, position, show, **extra):
        user = User.objects.create_user(username=SEED_USER + suffix, password="x")
        user.member_level = roles.LEVEL_FORMAL
        user.is_active = True
        user.position = position
        user.show_on_team = show
        for key, value in extra.items():
            setattr(user, key, value)
        user.save()
        return user

    made = {}
    made["chair"] = mk(
        "chair", position=chair, show=True,
        real_name="毕业照里的那个主席", grade="2023", college="集成电路学院",
        public_bio="统筹整体方向，平时在实验室折腾电源",
        avatar=png(), **SECRETS,
    )
    made["hw"] = mk(
        "hw", position=hw, show=True,
        real_name="没传头像的硬件主席", grade="2024", college="信息与通信工程学院",
    )
    # 刻意不写 public_bio：验「本人没写介绍时退回职位的 blurb」这条兜底
    made["custom"] = mk(
        "lead", position=custom, show=True,
        real_name="自建职位的部长", grade="2025", college="计算机科学与技术学院",
    )
    made["silent"] = mk(
        "silent", position=sw, show=False,
        real_name="没勾公开的软件主席", grade="2024", college="国家特色化示范性软件学院",
    )
    made["inactive"] = mk(
        "inactive", position=sw, show=True, is_active=False,
        real_name="停用账号的人", grade="2022", college="数学科学学院",
    )
    # 已经勾了公开展示、但没有职位 —— 依然不该上墙（这一页是现任团队，不是名册）
    made["plain"] = mk(
        "plain", position=None, show=True,
        real_name="没有职位的会员", grade="2025", college="物理与光电工程学院",
    )
    # 干干净净的一个人：没职位、没勾。留给「任命一下，看会不会顺手把他公开出去」
    made["fresh"] = mk(
        "fresh", position=None, show=False,
        real_name="刚被任命的人", grade="2026", college="机电工程学院",
    )

    medal = Medal.objects.create(name="自动化勋章·电赛国奖", icon="🥇", color="#c98a3d")
    UserMedal.objects.create(user=made["chair"], medal=medal, reason="自动化")

    return {k: v.pk for k, v in made.items()}


def live_summary():
    from django.contrib.auth import get_user_model

    return get_user_model().team_summary()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    import django

    SHOTS.mkdir(exist_ok=True)
    django.setup()

    from django.contrib.auth import get_user_model

    User = get_user_model()

    import dev_account

    # 职位管理是 @admin_required（其中三个职位自带驾驶舱权限），要等级 5
    user, password = dev_account.ensure(level=5)
    ids = seed()
    want = live_summary()
    print(f"已造 6 个账号（3 个该上墙）；在册聚合：{want}")

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

        # ---------------- 上墙口径 ----------------
        print("\n上墙口径：激活 + 本人同意 + 当前有职位，三个条件缺一不可")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        watch(page)
        page.goto(base + "/team/", wait_until="load")
        page.wait_for_timeout(500)
        st = page.evaluate(WALL)

        check(st["cards"] == 3, "墙上正好 3 张卡", f"{st['cards']} 张")
        check("毕业照里的那个主席" in st["names"], "勾了公开的在任成员上墙")
        check("没勾公开的软件主席" not in st["names"],
              "**任命但没勾公开展示的人不上墙**", str(st["names"]))
        check("停用账号的人" not in st["names"], "停用账号不上墙")
        check("没有职位的会员" not in st["names"],
              "没有职位的会员不上墙（这一页是现任团队，不是会员名册）")

        # 排序：职位按 sort_order（10 / 20 / 60），主席团自然在前
        check(st["posts"] == ["主席", "硬件主席", SEED_POSITION],
              "卡片按职位 sort_order 排序（10 / 20 / 60）", str(st["posts"]))
        check(st["cols"] > 1, "桌面多栏（一人一职位时按职位分节会读成一列空表）",
              f"{st['cols']} 列")
        # 职位色真的进了 CSS（--tm-accent 生效），而且各不相同
        check(len(st["postColors"]) == 3, "三枚职位徽章的颜色各不相同（--tm-accent 生效）",
              str(st["postColors"]))
        check(len(st["edgeColors"]) == 3, "卡片左缘也跟着职位色", str(st["edgeColors"]))
        # 职位色只染徽章和左缘。踩过同类的坑（荣誉墙那次等级色染到了奖项名上）。
        check(len(st["nameColors"]) == 1,
              "姓名一律同一个中性色（职位色不染姓名）", str(st["nameColors"]))
        # 本人没写介绍时退回职位的「这个职位做什么」，卡片不会只剩一个名字
        check(st["roleBios"] == ["带硬件方向的周常培训"],
              "没写介绍的人退回显示职位职责", str(st["roleBios"]))

        # ---------------- 隐私边界 ----------------
        print("\n隐私边界：姓名可以（本人同意过），联系方式一律不出现")
        html = page.content()
        for label, secret in SECRETS.items():
            check(secret not in html, f"页面源码里没有{label}", secret)
        text = page.evaluate("() => document.body.innerText")
        for label, secret in SECRETS.items():
            check(secret not in text, f"可见文本里没有{label}")

        # ---------------- 缺头像的样子 ----------------
        print("\n缺头像：渲染丝印首字母牌，不是碎图也不是空白")
        check(st["avatars"] == 1, "只有真的传了头像的那位是 <img>", f"{st['avatars']} 张")
        check(len(st["initials"]) == 2, "另外两位渲染首字母牌", str(st["initials"]))
        check(st["initials"] == ["没", "自"], "首字母取姓（中文取第一个字）", str(st["initials"]))

        shape = page.evaluate("""() => {
            const img = document.querySelector('.tm-avatar');
            const ini = document.querySelector('.tm-initial');
            const r = img.getBoundingClientRect();
            const q = ini.getBoundingClientRect();
            return {
                imgW: Math.round(r.width), imgH: Math.round(r.height),
                natural: img.naturalWidth,
                iniW: Math.round(q.width), iniH: Math.round(q.height),
            };
        }""")
        check(shape["natural"] > 0, "头像真的下载成功", f"naturalWidth={shape['natural']}")
        check(shape["imgW"] == shape["imgH"], "头像是正方形", f"{shape['imgW']}x{shape['imgH']}")
        # 有头像和没头像的两张卡必须一样高，否则一行里参差不齐
        check(shape["iniW"] == shape["imgW"] and shape["iniH"] == shape["imgH"],
              "首字母牌与头像同尺寸（同一行卡片不会参差）",
              f"{shape['iniW']}x{shape['iniH']} vs {shape['imgW']}x{shape['imgH']}")

        # ---------------- 聚合数字 ----------------
        print("\n聚合数字：现场重新数一遍，和页面上的比")
        check(st["heroNums"] and st["heroNums"][0] == str(want["total"]),
              "在册人数和实际一致", f"页面 {st['heroNums'][:1]} / 实际 {want['total']}")
        check(str(want["colleges"]) in st["heroNums"],
              "学院数一致", f"页面 {st['heroNums']} / 实际 {want['colleges']}")
        check("统筹整体方向" in " ".join(st["bios"]), "一句话介绍渲染出来了")
        check("23届" in st["cohorts"], "届别标识正确", str(st["cohorts"]))
        check(any("电赛国奖" in m for m in st["medals"]), "勋章渲染出来了", str(st["medals"]))
        check("下面这些" in st["heroText"], "有人在墙上时 Hero 才说「下面这些是…」")
        check(not errors, "无未捕获异常", "; ".join(errors[:2]))
        check(not failed, "无失败请求", "; ".join(failed[:3]))
        page.screenshot(path=str(SHOTS / "team-wall.png"), full_page=True)

        # 访客看不到站务提示
        check(not st["officerNote"], "访客看不到站务操作提示")
        ctx.close()

        # ---------------- 站务视角 ----------------
        print("\n站务视角：任命 ≠ 上墙，得看到「谁还没勾」")
        ctx = browser.new_context(viewport=vp)
        do_login(ctx, base, f"{user}:{password}")
        page = ctx.new_page()
        page.goto(base + "/team/", wait_until="load")
        page.wait_for_timeout(400)
        st2 = page.evaluate(WALL)
        check(st2["officerNote"], "站务看到操作提示")
        note = page.evaluate("() => document.querySelector('.tm-officer-note').innerText")
        want_pending = User.objects.filter(
            is_active=True, position__isnull=False, show_on_team=False,
        ).count()
        check(str(want_pending) in note,
              "提示里给出还没勾的人数（现场重新数一遍）",
              f"实际 {want_pending} · " + note.replace("\n", " ")[:70])

        page.goto(base + "/dashboard/positions/", wait_until="load")
        page.wait_for_timeout(400)
        dash = page.evaluate("""() => ({
            off: document.querySelectorAll('[data-optin="off"]').length,
            on: document.querySelectorAll('[data-optin="on"]').length,
            teamLink: !!document.querySelector('a[href="/team/"]'),
        })""")
        # 期望值现场从库里数 —— 开发库里可能本来就有别的在任成员，写死数字会
        # 在别人跑过一次之后莫名失败
        # 停用账号那一行显示「账号已停用」而不是 optin 徽章（无论勾没勾都不会上墙）
        want_on = User.objects.filter(
            is_active=True, position__isnull=False, show_on_team=True).count()
        want_off = User.objects.filter(
            is_active=True, position__isnull=False, show_on_team=False).count()
        check(dash["teamLink"], "驾驶舱能直达团队页")
        check(dash["on"] == want_on and dash["off"] == want_off,
              "逐行标出谁已公开、谁还没勾",
              f"页面 {dash['on']}/{dash['off']} · 实际 {want_on}/{want_off}")
        page.screenshot(path=str(SHOTS / "team-dashboard.png"), full_page=True)

        # 自建职位（不然这一页只能容下五个主席，「干事墙」无从存在）
        page.fill('input[name="name"]', "自动化职位·宣传干事")
        page.fill('input[name="blurb"]', "拍照剪片写公告")
        with page.expect_navigation(wait_until="load"):
            page.click("[data-position-create]")
        page.wait_for_timeout(300)
        from accounts.models import Position

        created = Position.objects.filter(name="自动化职位·宣传干事").first()
        check(created is not None, "管理员能自建职位")
        check(created is not None and not created.grants_management,
              "自建职位不授予驾驶舱权限（不开第二条提权入口）")
        if created:
            created.delete()

        # 任命一个人，确认没有顺手把他公开出去
        sw_pk = Position.objects.get(name="软件主席").pk
        fresh_pk = ids["fresh"]
        assign_js = """([posPk, userPk]) => {
            const form = [...document.querySelectorAll('form')].find(
                f => (f.querySelector('[name=form]') || {}).value === 'assign');
            form.querySelector('[name=position_id]').value = String(posPk);
            form.querySelector('[name=user_id]').value = String(userPk);
            form.submit();
        }"""
        with page.expect_navigation(wait_until="load"):
            page.evaluate(assign_js, [sw_pk, fresh_pk])
        page.wait_for_timeout(400)
        promoted = User.objects.get(pk=fresh_pk)
        check(promoted.position is not None, "任命成功")
        check(not promoted.show_on_team,
              "**任命没有替本人同意公开展示**（这一页压根不处理那个字段）")
        ctx.close()

        # 刚被任命的人还不该出现在墙上
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        page.goto(base + "/team/", wait_until="load")
        page.wait_for_timeout(300)
        st3 = page.evaluate(WALL)
        check("刚被任命的人" not in st3["names"],
              "刚任命、还没勾同意的人不出现在墙上", str(st3["names"]))
        ctx.close()

        # ---------------- 本人勾选 → 端到端 ----------------
        print("\n本人在个人资料页勾选（全站唯一入口），墙上立刻出现")
        target = User.objects.get(pk=fresh_pk)
        target.set_password("teambot-dev-only")
        target.save()
        ctx = browser.new_context(viewport=vp)
        do_login(ctx, base, f"{target.username}:teambot-dev-only")
        page = ctx.new_page()
        watch(page)
        page.goto(base + "/accounts/profile/edit/", wait_until="load")
        page.wait_for_timeout(300)
        pf = page.evaluate("""() => ({
            section: !!document.querySelector('.pf-team'),
            box: !!document.querySelector('#id_show_on_team'),
            bio: !!document.querySelector('#id_public_bio'),
            checked: (document.querySelector('#id_show_on_team') || {}).checked,
        })""")
        check(pf["section"] and pf["box"] and pf["bio"],
              "有职位的人看到「公开团队页」那一段")
        check(pf["checked"] is False, "默认不勾（默认不公开）")

        page.check("#id_show_on_team")
        page.fill("#id_public_bio", "自动化写的一句话介绍")
        # 走专用钩子而不是 button[type=submit]：这一页现在只有一张表单，但下次
        # 加个「删除头像」的小表单就会静默点错
        with page.expect_navigation(wait_until="load"):
            page.click("[data-profile-save]")
        page.wait_for_timeout(400)
        target.refresh_from_db()
        check(target.show_on_team, "勾选已保存")

        page.goto(base + "/team/", wait_until="load")
        page.wait_for_timeout(300)
        st4 = page.evaluate(WALL)
        check("刚被任命的人" in st4["names"], "勾完立刻出现在墙上", str(st4["names"]))
        check("自动化写的一句话介绍" in " ".join(st4["bios"]), "介绍也一起上了墙")

        # 取消勾选 → 立刻消失（不能只是「以后不再更新」）
        page.goto(base + "/accounts/profile/edit/", wait_until="load")
        page.wait_for_timeout(300)
        page.uncheck("#id_show_on_team")
        with page.expect_navigation(wait_until="load"):
            page.click("[data-profile-save]")
        page.wait_for_timeout(300)
        page.goto(base + "/team/", wait_until="load")
        page.wait_for_timeout(300)
        st5 = page.evaluate(WALL)
        check("刚被任命的人" not in st5["names"], "取消勾选后立刻从墙上消失")
        ctx.close()

        # 没有职位的人不该看到这一段（勾了也没反应的开关 = 坏界面）
        print("\n没有职位的人：不显示那个开关，也不能靠 POST 绕过")
        nobody = User.objects.get(pk=ids["silent"])
        nobody.position = None
        nobody.show_on_team = False
        nobody.set_password("teambot-dev-only")
        nobody.save()
        ctx = browser.new_context(viewport=vp)
        do_login(ctx, base, f"{nobody.username}:teambot-dev-only")
        page = ctx.new_page()
        page.goto(base + "/accounts/profile/edit/", wait_until="load")
        page.wait_for_timeout(300)
        gone = page.evaluate("""() => ({
            section: !!document.querySelector('.pf-team'),
            box: !!document.querySelector('#id_show_on_team'),
        })""")
        check(not gone["section"] and not gone["box"],
              "没有职位就不显示这一段（否则是一个勾了也没反应的开关）")
        ctx.close()

        # ---------------- 移动端 ----------------
        print("\n移动端（单栏，卡片保持横向）")
        ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                  is_mobile=True, has_touch=True, device_scale_factor=2)
        page = ctx.new_page()
        merrs = []
        page.on("pageerror", lambda e: merrs.append(str(e)))
        page.goto(base + "/team/", wait_until="load")
        page.wait_for_timeout(600)
        m = page.evaluate("""() => {
            const grid = document.querySelector('.tm-grid');
            const card = document.querySelector('.tm-card');
            const face = document.querySelector('.tm-face').getBoundingClientRect();
            const name = document.querySelector('.tm-name').getBoundingClientRect();
            return {
                vw: window.innerWidth,
                docW: document.documentElement.scrollWidth,
                cols: getComputedStyle(grid).gridTemplateColumns.split(' ').length,
                cardW: Math.round(card.getBoundingClientRect().width),
                faceW: Math.round(face.width),
                faceRight: Math.round(face.right),
                nameLeft: Math.round(name.left),
                heroTop: Math.round(document.querySelector('.page-hero h1').getBoundingClientRect().top),
                navBottom: Math.round(document.querySelector('.site-nav').getBoundingClientRect().bottom),
            };
        }""")
        check(m["docW"] <= m["vw"] + 1, "没有横向溢出", f"文档宽 {m['docW']} / 视口 {m['vw']}")
        check(m["cols"] == 1, "窄屏单栏", f"{m['cols']} 列")
        check(m["cardW"] > m["vw"] * 0.8, "卡片占满宽度", f"{m['cardW']}")
        # 断言的是「头像和文字并排」这件事本身，不是某个魔法高度 —— 卡片加一行
        # 内容高度就变，写死阈值的断言会在无关改动上假失败
        check(m["faceRight"] <= m["nameLeft"],
              "卡片保持横向排布（头像在文字左边，不是堆叠）",
              f"头像右缘 {m['faceRight']} / 姓名左缘 {m['nameLeft']}")
        check(m["faceW"] < 60, "窄屏头像位缩小", f"{m['faceW']}px")
        check(m["heroTop"] >= m["navBottom"], "标题没被固定导航切掉",
              f"{m['heroTop']} / {m['navBottom']}")
        check(not merrs, "移动端无未捕获异常", "; ".join(merrs[:2]))
        page.screenshot(path=str(SHOTS / "team-mobile.png"), full_page=True)
        ctx.close()

        # ---------------- 入口 ----------------
        print("\n入口：页脚 + 新生指南")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        watch(page)
        page.goto(base + "/", wait_until="load")
        page.wait_for_timeout(900)
        check(page.eval_on_selector_all(
            '.site-footer a[href="/team/"]', "els => els.length") == 1,
            "页脚快速入口里有团队页")
        page.goto(base + "/recruit/", wait_until="load")
        page.wait_for_timeout(500)
        check(page.eval_on_selector_all(
            '#intro a[href="/team/"]', "els => els.length") == 1,
            "新生指南「协会简介」里指向团队页")
        page.goto(base + "/privacy/", wait_until="load")
        page.wait_for_timeout(300)
        priv = page.evaluate("() => document.body.innerText")
        check("公开团队页" in priv, "隐私说明写了这一页的规则")
        check("默认不出现" in priv, "隐私说明写清了默认不公开")
        ctx.close()

        # ---------------- 空态 ----------------
        print("\n一个人都没勾时的空态")
        User.objects.filter(username__startswith=SEED_USER).update(show_on_team=False)
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        page.goto(base + "/team/", wait_until="load")
        page.wait_for_timeout(400)
        st6 = page.evaluate(WALL)
        check(st6["empty"], "渲染了设计过的空态（不是一片空白）")
        check(st6["cards"] == 0, "没有空壳卡片")
        check("新生指南" in st6["emptyText"], "空态给出了下一步")
        # Hero 那句话必须跟着变，否则它在指着一个空区块说「下面这些人」
        check("下面这些" not in st6["heroText"],
              "空态下 Hero 不再说「下面这些是…」", st6["heroText"].strip()[:60])
        # 聚合数字照常显示 —— 这是零 opt-in 时这一页的全部内容
        check(st6["heroNums"] and int(st6["heroNums"][0]) > 0,
              "在册人数照常显示（聚合数不是个人信息，不受开关约束）",
              str(st6["heroNums"]))
        page.screenshot(path=str(SHOTS / "team-empty.png"))
        ctx.close()

        browser.close()

    if "--keep" in sys.argv:
        seed()
        print("\n（--keep）已重新造好样例数据，可以直接 shoot.py --url /team/ 看")
    else:
        wipe()
    dev_account.ensure(level=4)

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("团队页契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
