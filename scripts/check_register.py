# -*- coding: utf-8 -*-
"""校验注册链路：选通道 → 分步填表 → 完成，以及登录 / 找回密码。

这条链路上有四类「坏了不报错」的东西，全都只有真的开一次浏览器才看得见：

  1. **分步表单**。HTML 里那张表本来完整可用，脚本只是「一次只显示一段」。
     所以要证明两件事：脚本在时能一段段走完并且拦住没填的必填项；脚本不在时
     三段全部展开、提交按钮可用。后者才是真正的底线。
  2. **条件字段**。「自定义方向」只在选了「自定义」时才该出现，藏起来时还要
     摘掉 required —— 否则浏览器会去校验一个看不见的必填框，报
     「An invalid form control is not focusable」：有报错、界面上没提示、
     用户只看到点了提交没反应。
  3. **验证码的服务端提示**。/accounts/send-code/ 返回的「该邮箱已注册」这类
     信息决定用户下一步干什么。注册页原来根本没有消息位，这些提示一个都看不见。
     顺带断言不再用 alert()（移动端是模态框，还抢焦点）。
  4. **`?next=` 的透传**。从招新页点「注册」的人注册完要回招新页。这个参数要过
     「选通道 → 填表 → POST」三跳，中间丢了不会有任何报错。

跑法：python scripts/check_register.py
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
# Playwright 的同步 API 在 Django 看来是异步上下文，块内任何 ORM 调用都会抛
# SynchronousOnlyOperation。仅开发脚本用。
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

from shoot import PORT, DevServer  # noqa: E402

SHOTS = REPO / ".shots"
failures = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


FORM = """
() => {
    const form = document.getElementById('reg-form');
    if (!form) return null;
    const steps = [...form.querySelectorAll('[data-step]')];
    const sub = form.querySelector('[data-step-submit]');
    const next = form.querySelector('[data-step-next]');
    const prev = form.querySelector('[data-step-prev]');
    const custom = form.querySelector('[data-show-when]');
    const customInput = custom && custom.querySelector('input, select, textarea');
    const dots = [...form.querySelectorAll('[data-step-dots] > li')];
    return {
        stepped: form.classList.contains('is-stepped'),
        noValidate: form.noValidate,
        totalSteps: steps.length,
        visibleSteps: steps.filter(s => !s.hidden).length,
        visibleIndex: steps.findIndex(s => !s.hidden),
        submitHidden: sub ? sub.hidden : null,
        nextHidden: next ? next.hidden : null,
        prevHidden: prev ? prev.hidden : null,
        // hidden 属性 + tokens.css 的全局 [hidden] 才等于真的看不见
        submitBox: sub ? sub.getBoundingClientRect().height : -1,
        customHidden: custom ? custom.hidden : null,
        customRequired: customInput ? customInput.required : null,
        dotStates: dots.map(d => d.className),
        review: (form.querySelector('.reg-review') || {}).textContent || '',
    };
}
"""

CODE_MSG = """
() => {
    const slot = document.querySelector('[data-code-msg]');
    return {
        text: slot ? slot.textContent.trim() : '(no slot)',
        cls: slot ? slot.className : '',
    };
}
"""

# 三块内容都必须落在固定导航以下、视口以内。窄屏溢出在桌面尺寸下永远看不到。
MOBILE_FIT = """
() => {
    const nav = document.querySelector('.site-nav');
    const navBottom = nav ? nav.getBoundingClientRect().bottom : 0;
    const pick = (sel) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { top: Math.round(r.top), bottom: Math.round(r.bottom),
                 w: Math.round(r.width) };
    };
    const firstField = document.querySelector(
        '[data-step]:not([hidden]) input, [data-step]:not([hidden]) select');
    return {
        navBottom: Math.round(navBottom),
        vw: window.innerWidth,
        vh: window.innerHeight,
        head: pick('.auth-head'),
        panel: pick('.auth-panel'),
        extra: pick('.auth-extra'),
        step: pick('[data-step]:not([hidden])'),
        firstFieldTop: firstField
            ? Math.round(firstField.getBoundingClientRect().top) : -1,
    };
}
"""


def django_setup():
    import django

    django.setup()


def reset_e2e(username: str, email: str) -> None:
    """把端到端要用的账号与验证码清干净（脚本要能反复跑）。"""
    from django.contrib.auth import get_user_model

    from accounts.models import VerificationCode

    get_user_model().objects.filter(username=username).delete()
    get_user_model().objects.filter(email__iexact=email).delete()
    VerificationCode.objects.filter(email__iexact=email).delete()


def latest_code(email: str) -> str | None:
    """读服务端刚发出的验证码。

    dev 的邮件后端是 console，收不到信；而这条链路的重点是「表单能不能走通」，
    不是「邮件能不能送达」。所以直接从库里取那一条。
    """
    from accounts.models import VerificationCode

    row = (VerificationCode.objects
           .filter(email__iexact=email, purpose="register", used=False)
           .order_by("-created_at").first())
    return row.code if row else None


def user_level(username: str) -> int | None:
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.filter(username=username).first()
    return int(user.member_level) if user else None


def close_campaigns() -> None:
    from recruitment.models import Campaign

    Campaign.objects.update(is_active=False)


TEST_CAMPAIGN = "自动化测试批次"


def reopen_campaign() -> None:
    """开发库里保证有且只有一个进行中的批次。

    **开头和结尾都要调用**：脚本中途会把批次全关掉来验完成页，一旦崩在中间就
    留下一个「没有开放批次」的库，下次跑到端到端那段又会走完成页而不是跳报名页
    —— 表现为一条莫名其妙的失败。踩过一次。

    先按名字删再建，不要 update_or_create：同名批次会累积（其它检查脚本也建
    同名的），get() 直接抛 MultipleObjectsReturned。
    """
    from django.utils import timezone

    from recruitment.models import Campaign

    Campaign.objects.filter(name=TEST_CAMPAIGN).delete()
    Campaign.objects.update(is_active=False)
    now = timezone.now()
    Campaign.objects.create(
        name=TEST_CAMPAIGN, is_active=True,
        opens_at=now - timezone.timedelta(days=1),
        closes_at=now + timezone.timedelta(days=12),
        intro="",
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(exist_ok=True)
    django_setup()

    import dev_account

    dev_account.ensure(level=1)
    taken_email = dev_account.EMAIL
    # 批次状态必须在 DevServer 起来**之前**摆好：招新状态在服务端缓存 5 分钟，
    # 而 dev 用进程内 LocMem，外部脚本没法让它失效。新进程的缓存才是冷的。
    reopen_campaign()
    print(f"已注册邮箱（用于验重复提示）：{taken_email} · 批次已就绪")

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        base = f"http://127.0.0.1:{PORT}"
        vp = {"width": 1440, "height": 1000}

        # ---------------- 选通道 ----------------
        print("\n第一步：选通道")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        resp = page.goto(base + "/accounts/register/?next=/recruitment/",
                         wait_until="load")
        cache = (resp.headers.get("cache-control") or "")
        check("no-store" in cache, "注册页响应头是 no-store（不落盘）", cache)

        hrefs = page.eval_on_selector_all(
            ".reg-channel", "els => els.map(e => e.getAttribute('href'))")
        check(len(hrefs) == 2, "两条通道都在", str(len(hrefs)))
        check(all("next=" in (h or "") for h in hrefs),
              "两条通道链接都带上了 next（三跳里最容易丢的一跳）", str(hrefs))
        page.screenshot(path=str(SHOTS / "register-choice.png"))
        ctx.close()

        # ---------------- 分步表单 ----------------
        print("\n第二步：分步填表（脚本已接管）")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        dialogs = []
        page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base + "/accounts/register/new/?next=/recruitment/",
                  wait_until="load")
        page.wait_for_timeout(500)

        st = page.evaluate(FORM)
        check(st is not None, "注册表单已渲染")
        check(st["stepped"], "脚本已接管（form 上有 .is-stepped）")
        # Django 的 UserCreationForm 会给 username 挂 autofocus，而分步之后它在
        # 第三段里。autofocus 在 HTML 解析时生效、早于 defer 的脚本，浏览器会把
        # 它滚进视口，脚本随后收起后两段 —— 页面就停在底部，标题和前几个字段
        # 都在视口外。控制台一声不响，只有截图和这条断言能发现。
        check(page.evaluate("() => Math.round(window.scrollY)") < 40,
              "打开时停在页面顶部（没有被 autofocus 滚到底）",
              f"scrollY={page.evaluate('() => Math.round(window.scrollY)')}")
        check(st["totalSteps"] == 3, "表单分三段", f"{st['totalSteps']} 段")
        check(st["visibleSteps"] == 1, "一次只显示一段", f"可见 {st['visibleSteps']} 段")
        check(st["noValidate"] is True,
              "接管后关掉原生校验（否则会校验看不见的字段）")
        check(st["submitHidden"] is True and st["submitBox"] == 0,
              "非最后一段时提交按钮收起（且 [hidden] 真的生效）",
              f"高度 {st['submitBox']}")
        check(st["nextHidden"] is False and st["prevHidden"] is True,
              "第一段只有「下一步」")
        check(page.eval_on_selector("[name=next]", "el => el.value") == "/recruitment/",
              "next 已存进隐藏域，POST 回来不会丢")

        # 条件字段：默认藏起来，且 required 已摘掉
        check(st["customHidden"] is True, "「自定义方向」默认收起（没选自定义）")
        check(st["customRequired"] is False,
              "收起时 required 已摘掉（否则报 not focusable、有错无提示）")
        page.select_option("#id_specialty", "custom")
        page.wait_for_timeout(150)
        st = page.evaluate(FORM)
        check(st["customHidden"] is False, "选了「自定义」就把方向输入框放出来")
        page.select_option("#id_specialty", "hardware")
        page.wait_for_timeout(150)
        check(page.evaluate(FORM)["customHidden"] is True, "选回硬件又收起来")

        # 必填拦截：第一段还没填就点下一步，应当推不动
        page.click("[data-step-next]")
        page.wait_for_timeout(200)
        check(page.evaluate(FORM)["visibleIndex"] == 0,
              "第一段必填没填时推不动（被自己的 checkValidity 拦住）")

        page.fill("#id_real_name", "自动化小明")
        page.fill("#id_student_id", "2026999001")
        page.select_option("#id_college", index=1)
        page.select_option("#id_grade", index=1)
        page.select_option("#id_specialty", "hardware")
        page.click("[data-step-next]")
        page.wait_for_timeout(250)
        st = page.evaluate(FORM)
        check(st["visibleIndex"] == 1 and st["prevHidden"] is False,
              "填完第一段推进到第二段，出现「上一步」")
        check("is-done" in st["dotStates"][0] and "is-current" in st["dotStates"][1],
              "进度点跟着走", str(st["dotStates"]))

        # ---------------- 验证码的服务端提示 ----------------
        print("\n验证码：服务端说的话必须显示出来")
        page.click("[data-send-code]")
        page.wait_for_timeout(300)
        msg = page.evaluate(CODE_MSG)
        check(msg["text"] != "(no slot)", "验证码字段有消息位")
        check("邮箱" in msg["text"], "邮箱没填时就地提示（不是 alert）", msg["text"])
        check(not dialogs, "没有弹出 alert 对话框", str(dialogs[:1]))

        page.fill("#id_email", taken_email)
        page.click("[data-send-code]")
        page.wait_for_timeout(900)
        msg = page.evaluate(CODE_MSG)
        check("已注册" in msg["text"],
              "已注册的邮箱会看到服务端返回的原因", msg["text"])
        check("code-msg-err" in msg["cls"], "失败提示是错误配色", msg["cls"])

        # ---------------- 走到最后一段看确认清单 ----------------
        print("\n第三步：确认清单")
        page.fill("#id_email", "auto-check@heuesta.invalid")
        page.fill("#id_code", "000000")
        page.fill("#id_phone", "13900000001")
        page.click("[data-step-next]")
        page.wait_for_timeout(250)
        st = page.evaluate(FORM)
        check(st["visibleIndex"] == 2, "推进到最后一段", f"第 {st['visibleIndex']} 段")
        check(st["submitHidden"] is False and st["nextHidden"] is True,
              "最后一段出现提交按钮、隐藏「下一步」")
        check("自动化小明" in st["review"] and "2026999001" in st["review"],
              "确认清单回显了前两段填的内容", st["review"].replace("\n", " ")[:70])
        check("auto-check@heuesta.invalid" in st["review"], "邮箱也回显了")
        page.screenshot(path=str(SHOTS / "register-step3.png"))
        check(not errors, "无未捕获异常", "; ".join(errors[:2]))
        ctx.close()

        # ---------------- 服务端错误要能被看见 ----------------
        print("\n服务端退回的错误必须停在出错的那一段")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        page.goto(base + "/accounts/register/new/", wait_until="load")
        page.wait_for_timeout(400)
        # 验证码故意填错 —— 服务端会把错误挂在 code 字段上，而它在第二段里。
        # 退回后必须停在那一段，否则用户看到的是一张「没有任何问题」的表。
        #
        # 直接用 JS 灌值而不是 page.fill()：分步之后第二、三段是 hidden 的，
        # Playwright 拒绝填不可见的元素（这一条卡了一次）。这里要测的是服务端
        # 往返，不是逐段交互，所以绕过可见性是对的。
        page.evaluate("""() => {
            const v = {
                real_name: '自动化小红', student_id: '2026999002',
                email: 'auto-err@heuesta.invalid', code: '000000',
                phone: '13900000002', username: 'autocheckbot',
                password1: 'Str0ngPass!2026', password2: 'Str0ngPass!2026',
            };
            const form = document.getElementById('reg-form');
            Object.keys(v).forEach(k => {
                const el = form.querySelector('[name="' + k + '"]');
                if (el) el.value = v[k];
            });
            ['college', 'grade'].forEach(k => {
                const sel = form.querySelector('[name="' + k + '"]');
                if (sel) sel.selectedIndex = 1;
            });
            form.querySelector('[name="specialty"]').value = 'hardware';
            form.querySelector('[name="privacy_consent"]').checked = true;
        }""")
        # 用 expect_navigation 包住提交。`evaluate(form.submit())` 之后再
        # wait_for_load_state 会和导航赛跑：执行上下文被销毁，evaluate 直接抛
        # 「Execution context was destroyed」。踩过一次。
        with page.expect_navigation(wait_until="load"):
            page.evaluate("() => document.getElementById('reg-form').submit()")
        page.wait_for_timeout(500)
        st = page.evaluate(FORM)
        check(st is not None and st["stepped"], "退回后脚本仍然接管")
        check(st and st["visibleIndex"] == 1,
              "停在出错的那一段（验证码在第二段）", f"第 {st['visibleIndex'] if st else '?'} 段")
        has_err = page.eval_on_selector_all(
            "[data-step]:not([hidden]) .form-error", "els => els.length")
        check(has_err > 0, "那一段里能看见错误提示", f"{has_err} 条")
        ctx.close()

        # ---------------- 端到端：真的注册成一个账号 ----------------
        # 这是整条链路唯一真正重要的契约。上面每一条都可能全绿而人还是注册不了
        # （比如某个隐藏字段没提交、验证码没对上、跳转目标算错）。
        # dev 的邮件后端是 console，不会真的发信。
        print("\n端到端：走完三段真的注册成功")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        e2e_user = "e2ebot2026"
        e2e_email = "e2e@heuesta.invalid"
        reset_e2e(e2e_user, e2e_email)
        page.goto(base + "/accounts/register/new/", wait_until="load")
        page.wait_for_timeout(400)

        page.fill("#id_real_name", "端到端小明")
        page.fill("#id_student_id", "2026999777")
        page.select_option("#id_college", index=1)
        page.select_option("#id_grade", index=1)
        page.select_option("#id_specialty", "hardware")
        page.click("[data-step-next]")
        page.wait_for_timeout(200)

        page.fill("#id_email", e2e_email)
        page.click("[data-send-code]")
        page.wait_for_timeout(900)
        msg = page.evaluate(CODE_MSG)
        check("已发送" in msg["text"], "验证码发送成功的提示也显示出来了", msg["text"])
        code = latest_code(e2e_email)
        check(bool(code), "服务端确实生成了验证码", str(code))
        page.fill("#id_code", code or "")
        page.fill("#id_phone", "13900007777")
        page.click("[data-step-next]")
        page.wait_for_timeout(200)

        page.fill("#id_username", e2e_user)
        page.fill("#id_password1", "Str0ngPass!2026")
        page.fill("#id_password2", "Str0ngPass!2026")
        page.check("#id_privacy_consent")
        page.click("[data-step-submit]")
        page.wait_for_load_state("load")
        page.wait_for_timeout(600)

        check(page.url.endswith("/recruitment/"),
              "有开放批次时直接送到报名页", page.url)
        level = user_level(e2e_user)
        check(level == 1, "账号建好了且是招新成员（等级 1）", f"等级 {level}")
        body = page.eval_on_selector("body", "el => el.textContent")
        check("注册成功" in body, "报名页顶部给了注册成功的反馈")
        page.screenshot(path=str(SHOTS / "register-landed.png"))
        ctx.close()

        # ---------------- 没有开放批次时走完成页 ----------------
        print("\n没有开放批次：完成页而不是死胡同")
        close_campaigns()
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        e2e2_user = "e2ebot2026b"
        e2e2_email = "e2eb@heuesta.invalid"
        reset_e2e(e2e2_user, e2e2_email)
        page.goto(base + "/accounts/register/new/", wait_until="load")
        page.wait_for_timeout(400)
        # 这次不逐段点，直接灌值提交 —— 分步交互上面已经验过了
        page.evaluate("""(v) => {
            const form = document.getElementById('reg-form');
            Object.keys(v).forEach(k => {
                const el = form.querySelector('[name="' + k + '"]');
                if (el) el.value = v[k];
            });
            ['college', 'grade'].forEach(k => {
                form.querySelector('[name="' + k + '"]').selectedIndex = 1;
            });
            form.querySelector('[name="specialty"]').value = 'hardware';
            form.querySelector('[name="privacy_consent"]').checked = true;
        }""", {
            "real_name": "完成页小红", "student_id": "2026999778",
            "email": e2e2_email, "phone": "13900007778",
            "username": e2e2_user,
            "password1": "Str0ngPass!2026", "password2": "Str0ngPass!2026",
        })
        page.evaluate("""async () => {
            const r = await fetch('/accounts/send-code/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || '',
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({
                    email: document.getElementById('id_email').value,
                    purpose: 'register',
                }).toString(),
                credentials: 'same-origin',
            });
            return r.status;
        }""")
        page.wait_for_timeout(400)
        code2 = latest_code(e2e2_email)
        page.evaluate("(c) => { document.getElementById('id_code').value = c; }", code2 or "")
        with page.expect_navigation(wait_until="load"):
            page.evaluate("() => document.getElementById('reg-form').submit()")
        page.wait_for_timeout(500)
        done = page.evaluate("""() => ({
            title: (document.querySelector('.auth-h1') || {}).textContent || '',
            text: document.body.textContent.replace(/\\s+/g, ' '),
            ladder: document.querySelectorAll('.lv-step.is-done').length,
            actions: [...document.querySelectorAll('.rec-actions a')].map(a => a.getAttribute('href')),
        })""")
        check("账号已就位" in done["title"], "落在完成页而不是「招新通道暂时关闭」",
              done["title"].strip())
        check(user_level(e2e2_user) == 1, "账号照样是可用的招新成员")
        check(done["ladder"] >= 2, "等级阶梯点亮到「招新成员」", f"{done['ladder']} 级已亮")
        check(len(done["actions"]) >= 2, "给了下一步可点（不是死胡同）", str(done["actions"]))
        page.screenshot(path=str(SHOTS / "register-done.png"))
        ctx.close()
        reopen_campaign()

        # ---------------- 脚本挂了：三段全展开 ----------------
        print("\n分步脚本加载失败（表单必须照常可用）")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        page.route("**/js/form-enhance*.js", lambda r: r.fulfill(status=404, body=""))
        page.goto(base + "/accounts/register/new/", wait_until="load")
        page.wait_for_timeout(500)
        st = page.evaluate(FORM)
        check(not st["stepped"], "脚本没接管")
        check(st["visibleSteps"] == 3, "三段全部展开", f"可见 {st['visibleSteps']} 段")
        check(st["submitHidden"] is False and st["submitBox"] > 0,
              "提交按钮可用（没有 JS 也能交）")
        check(st["noValidate"] is False,
              "原生校验还在（HTML 里不能写 novalidate）")
        check(st["customHidden"] is False,
              "「自定义方向」可见（没有 JS 时信息不能丢）")
        ctx.close()

        # ---------------- 登录页 ----------------
        print("\n登录页")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        resp = page.goto(base + "/accounts/login/?next=/recruitment/", wait_until="load")
        check("no-store" in (resp.headers.get("cache-control") or ""),
              "登录页响应头是 no-store")
        segs = page.eval_on_selector_all(
            ".auth-seg a",
            "els => els.map(e => ({t: e.textContent.trim(), h: e.getAttribute('href'),"
            " cur: e.classList.contains('is-current')}))")
        check(len(segs) == 2, "两种登录方式都露在外面（分段控件）", str(len(segs)))
        check(sum(1 for s in segs if s["cur"]) == 1, "当前方式只高亮一个")
        check(all("next=" in (s["h"] or "") for s in segs),
              "两个方式互跳都带着 next")
        check(page.eval_on_selector("[name=next]", "el => el.value") == "/recruitment/",
              "登录表单里 next 就位")
        page.screenshot(path=str(SHOTS / "login.png"))
        ctx.close()

        # ---------------- 移动端 ----------------
        print("\n移动端（单栏，三块都要落在导航以下视口以内）")
        ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                  is_mobile=True, has_touch=True,
                                  device_scale_factor=2)
        page = ctx.new_page()
        merrs = []
        page.on("pageerror", lambda e: merrs.append(str(e)))
        page.goto(base + "/accounts/register/new/", wait_until="load")
        page.wait_for_timeout(600)
        fit = page.evaluate(MOBILE_FIT)
        st = page.evaluate(FORM)
        check(st["visibleSteps"] == 1, "移动端照样只显示一段")
        check(fit["head"]["w"] > fit["vw"] * 0.8 and fit["panel"]["w"] > fit["vw"] * 0.8,
              "两栏已堆叠成单栏（各自占满宽度）",
              f"标题 {fit['head']['w']} / 面板 {fit['panel']['w']} / 视口 {fit['vw']}")
        check(fit["step"]["top"] >= fit["navBottom"],
              "当前段没有被固定导航切掉",
              f"段顶 {fit['step']['top']} / 导航底 {fit['navBottom']}")
        # 窄屏重排的目的就是这一条：注册页的主要动作是填表，第一个输入框不能被
        # 整个说明栏推到首屏之外（原来在 732px 处，844 高的视口里已经看不见）。
        check(0 < fit["firstFieldTop"] < fit["vh"],
              "第一个输入框在首屏之内（说明栏没把表单挤下去）",
              f"框顶 {fit['firstFieldTop']} / 视口高 {fit['vh']}")
        check(fit["extra"]["top"] > fit["panel"]["top"],
              "补充说明排到了表单之后",
              f"说明 {fit['extra']['top']} / 表单 {fit['panel']['top']}")
        check(not merrs, "移动端无未捕获异常", "; ".join(merrs[:2]))
        page.screenshot(path=str(SHOTS / "register-mobile.png"), full_page=True)
        ctx.close()

        browser.close()

    # 收尾：把开发账号恢复成站务级（其它截图脚本按这个假设写的）
    dev_account.ensure(level=4)

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("注册链路契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
