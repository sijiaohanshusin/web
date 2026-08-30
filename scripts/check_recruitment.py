# -*- coding: utf-8 -*-
"""校验招新落地页的四种状态与分步表单。

这一页的复杂度全在**状态分支**上：同一个 URL 对不同人显示完全不同的东西 ——
未登录 / 可报名 / 已报名 / 已是会员 / 已关闭 / 连批次都没有。任何一支写错都不会
报错，只会让某一类人看到不该看的东西（最糟的是「已经报过名的人又看到一张空表」）。
所以逐个把用户和数据切到那个状态，真的打开页面看渲染出了哪一支。

分步表单那部分守的是**渐进增强**：HTML 里那张表本来就完整可用，脚本只是「一次
只显示一段」。所以要证明两件事：脚本在时分步真的能走完，脚本不在时三段全展开且
提交按钮可用。

跑法：python scripts/check_recruitment.py
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
# 这个脚本要在浏览器检查之间改数据库状态（建报名、改进展、关批次），而
# Playwright 的同步 API 跑在 greenlet 上、在 Django 看来就是个事件循环，于是
# 任何 ORM 调用都会抛 SynchronousOnlyOperation。这个开关正是为这种「我确定不在
# 真正的事件循环里」的场景提供的。仅开发脚本用。
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

from shoot import PORT, DevServer, do_login  # noqa: E402

SHOTS = REPO / ".shots"
URL = "/recruitment/"
failures = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


PANEL = """
() => {
    const box = document.querySelector('.rec-box');
    const form = document.getElementById('rec-form');
    const steps = [...document.querySelectorAll('[data-step]')];
    const sub = form && form.querySelector('[data-step-submit]');
    const next = form && form.querySelector('[data-step-next]');
    const prev = form && form.querySelector('[data-step-prev]');
    const dotBox = form && form.querySelector('[data-step-dots]');
    return {
        dots: dotBox ? dotBox.children.length : 0,
        // 停在第几段（0 起）。服务端退回错误时脚本应当落在出错的那一段上。
        currentStep: steps.findIndex(s => !s.hidden),
        stepErrors: steps.map(s => s.querySelectorAll('.form-error').length),
        // 多选组：这一组有没有一个能被读屏软件念出来的名字。
        // 名字由外层 fieldset 的 legend 承担 —— 而**典型故障是走了
        // includes/field.html**：CheckboxSelectMultiple 的 id_for_label 返回一个
        // 没有任何 input 拥有的 id，label 的 for 落空、这一组就没有名字了，
        // 而页面看起来完全正常。所以顺带数一下有多少个 for 指向不存在的元素。
        groups: [...document.querySelectorAll('.rec-check')].map(g => {
            const fs = g.closest('fieldset');
            const legend = fs && fs.querySelector('legend');
            const labels = fs ? [...fs.querySelectorAll('label[for]')] : [];
            return {
                boxes: g.querySelectorAll('input[type=checkbox]').length,
                groupName: legend ? legend.textContent.trim() : '',
                danglingFor: labels
                    .filter(l => !document.getElementById(l.getAttribute('for')))
                    .map(l => l.getAttribute('for')),
            };
        }),
        heading: box ? (box.querySelector('h2') || {}).textContent || '' : '(no panel)',
        text: box ? box.textContent.replace(/\\s+/g, ' ').trim() : '',
        hasForm: !!form,
        stepped: form ? form.classList.contains('is-stepped') : false,
        visibleSteps: steps.filter(s => !s.hidden).length,
        totalSteps: steps.length,
        submitHidden: sub ? sub.hidden : null,
        nextHidden: next ? next.hidden : null,
        prevHidden: prev ? prev.hidden : null,
        track: [...document.querySelectorAll('.rec-track-item')]
            .map(li => li.classList.contains('is-done')),
        heroTitle: (document.querySelector('.rec-hero-title') || {}).textContent || '',
        leadStat: (document.querySelector('.rec-stat-lead strong') || {}).textContent || '',
        emptyStat: !!document.querySelector('.rec-stats-empty'),
    };
}
"""


def django_setup():
    import django

    django.setup()


def set_level(level: int):
    import dev_account

    return dev_account.ensure(level=level)


def open_campaign(days: int = 12):
    from django.utils import timezone

    from recruitment.models import Campaign

    # 先按名字删掉旧的：不删的话每跑一次就多一条同名批次，开发库里会堆出一串，
    # 别的脚本按名字取时直接抛 MultipleObjectsReturned。
    Campaign.objects.filter(name="自动化测试批次").delete()
    Campaign.objects.update(is_active=False)
    now = timezone.now()
    return Campaign.objects.create(
        name="自动化测试批次", is_active=True,
        opens_at=now - timezone.timedelta(days=1),
        closes_at=now + timezone.timedelta(days=days),
        intro="",
    )


def wipe_applications(user_name="shootbot"):
    from recruitment.models import Application

    Application.objects.filter(user__username=user_name).delete()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(exist_ok=True)
    django_setup()

    # 招新状态在服务端缓存 5 分钟、dev 又是进程内 LocMem，外部脚本没法让它失效 ——
    # 所以批次必须在 DevServer 起来之前建好，新进程的缓存才是冷的。
    campaign = open_campaign()
    wipe_applications()
    user, password = set_level(1)          # 招新成员：能看到报名表那一支
    print(f"批次 {campaign.name} · 账号 {user}")

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        base = f"http://127.0.0.1:{PORT}"
        vp = {"width": 1440, "height": 1000}

        def open_page(login=True):
            ctx = browser.new_context(viewport=vp)
            if login:
                do_login(ctx, base, f"{user}:{password}")
            page = ctx.new_page()
            page.goto(base + URL, wait_until="load")
            page.wait_for_timeout(500)
            return ctx, page

        # ---------------- 未登录 ----------------
        print("\n未登录")
        ctx, page = open_page(login=False)
        st = page.evaluate(PANEL)
        check("账号" in st["heading"] or "登录" in st["heading"],
              "右栏是「先有账号再报名」", st["heading"].strip())
        check(not st["hasForm"], "不渲染报名表（没账号填了也没用）")
        check("注册" in st["text"] and "登录" in st["text"], "给了注册与登录两个入口")
        ctx.close()

        # ---------------- 可报名：分步表单 ----------------
        print("\n可报名（招新成员，未报名）")
        ctx, page = open_page()
        st = page.evaluate(PANEL)
        check(st["hasForm"], "渲染了报名表")
        check(st["totalSteps"] == 5, "表单分五段", f"{st['totalSteps']} 段")
        check(st["dots"] == st["totalSteps"],
              "步骤点数量和段数一致（对不上的话最后一段的点永远不亮，进度条在撒谎）",
              f"{st['dots']} 点 / {st['totalSteps']} 段")
        check(st["stepped"], "脚本已接管（form 上有 .is-stepped）")
        check(st["visibleSteps"] == 1, "一次只显示一段", f"可见 {st['visibleSteps']} 段")
        check(st["submitHidden"] is True, "非最后一段时提交按钮收起")
        check(st["nextHidden"] is False and st["prevHidden"] is True,
              "第一段只有「下一步」")
        check(st["emptyStat"], "零报名时不显示「0 人已报名」而是换一句话")

        # 多选组的无障碍名字。这一条是新加的：多选组**不能**走
        # includes/field.html，那份的 label[for] 会指向一个不存在的 id。
        check(len(st["groups"]) == 2, "两个多选组都渲染了", f"{len(st['groups'])} 组")
        for i, g in enumerate(st["groups"]):
            check(bool(g["groupName"]), f"多选组 {i + 1} 有可访问的组名（fieldset 的 legend）",
                  g["groupName"])
            check(g["boxes"] >= 5, f"多选组 {i + 1} 的选项数对得上", f"{g['boxes']} 项")
            check(not g["danglingFor"],
                  f"多选组 {i + 1} 所在段里没有落空的 label[for]（读屏软件念不出组名的典型原因）",
                  ",".join(g["danglingFor"]))

        # ---- 走完五段 ----
        # 每段的字段不同，所以逐段填。`page.fill` 填不了被藏起来的字段，
        # 所以顺序必须跟着分步走。
        page.click('.rec-choice-item:has(input[value="hardware"]) input')
        page.click("[data-step-next]")
        page.wait_for_timeout(200)
        st = page.evaluate(PANEL)
        check(st["visibleSteps"] == 1 and st["prevHidden"] is False,
              "推进到第二段，出现「上一步」")

        # 第二段：兴趣方向多选 + 其他补充
        page.check('.rec-check-item:has(input[value="mcu"]) input')
        page.check('.rec-check-item:has(input[value="dsp_fpga"]) input')
        page.click("[data-step-next]")
        page.wait_for_timeout(200)
        check(page.evaluate(PANEL)["currentStep"] == 2, "推进到第三段")

        # 第三段：性别 / 出生日期（写 User）+ 经历
        page.select_option('[name="gender"]', "female")
        page.fill('[name="birthday"]', "2007-11-23")
        page.fill('[name="skills"]', "焊过几块板子")
        page.click("[data-step-next]")
        page.wait_for_timeout(200)
        check(page.evaluate(PANEL)["currentStep"] == 3, "推进到第四段")

        # 第四段：三个开放题，只有自我介绍必填
        page.fill('[name="self_intro"]', "零基础但很想学，想跟着做电赛的题目练手。")
        page.click("[data-step-next]")
        page.wait_for_timeout(200)
        st = page.evaluate(PANEL)
        check(st["submitHidden"] is False and st["nextHidden"] is True,
              "最后一段出现提交按钮、隐藏「下一步」")

        # 第五段：渠道多选 + 确认回显
        page.check('.rec-check-item:has(input[value="senior"]) input')
        page.wait_for_timeout(120)
        review = page.eval_on_selector(".rec-review",
                                       "el => el.textContent.replace(/\\s+/g,' ')")
        check("硬件部" in review and "焊过几块板子" in review,
              "确认页回显了单选与文本框", review.strip()[:70])
        # **多选的回显走 form-enhance.js 里 checkbox 那一支**（多个同名控件时
        # 把勾上的 label 文字用「、」连起来）。它本来就支持，这里是钉住它没被改坏。
        check("单片机编程与设计" in review and "DSP / FPGA 应用设计" in review,
              "确认页把多选回显成中文标签（不是 mcu,dsp_fpga）", review.strip()[:70])
        page.screenshot(path=str(SHOTS / "recruitment-form.png"))

        # 必填拦截：回到第四段清空自我介绍，应当推不动
        page.click("[data-step-prev]")
        page.wait_for_timeout(150)
        page.fill('[name="self_intro"]', "")
        page.click("[data-step-next]")
        page.wait_for_timeout(200)
        st = page.evaluate(PANEL)
        check(st["submitHidden"] is True, "必填项没填时推不到最后一段（被拦住）")
        ctx.close()

        # ---- 多选的「至少选一项」只能靠服务端 ----
        # Django 的 CheckboxSelectMultiple **刻意不发 `required` 属性**（对一组
        # 复选框来说 `required` 的语义会变成「必须勾这一个」），所以
        # form-enhance.js 的 `checkValidity()` 拦不住「一个都没勾」—— 它只能一路
        # 放行到提交。于是这一条的可用性全靠「服务端退回的错误必须能被看见」：
        # 脚本初始化时要停在**第一个带错误的那一段**上。
        print("\n多选一个都没勾：服务端拦下来，且要停在出错的那一段")
        ctx, page = open_page()
        # 用 evaluate 灌值而不是 fill：后面几段此刻是隐藏的，fill 拒绝操作
        # 不可见元素（30 秒超时）。
        page.evaluate("""() => {
            const f = document.getElementById('rec-form');
            f.querySelector('input[name=department][value=hardware]').checked = true;
            f.querySelector('[name=self_intro]').value = '零基础但很想学，想跟着做电赛的题目练手。';
            f.querySelectorAll('input[name=interests]').forEach(b => { b.checked = false; });
            f.querySelectorAll('input[name=heard_from]').forEach(b => { b.checked = false; });
        }""")
        with page.expect_navigation():
            page.evaluate("() => document.getElementById('rec-form').submit()")
        page.wait_for_timeout(500)
        st = page.evaluate(PANEL)
        check(st["hasForm"], "服务端退回后仍然是那张表（没有报名成功）")
        check(sum(st["stepErrors"]) > 0, "页面上真的显示了错误", str(st["stepErrors"]))
        first_bad = next((i for i, n in enumerate(st["stepErrors"]) if n), None)
        check(st["currentStep"] == first_bad,
              "**停在第一个带错误的那一段**（否则用户看到一张「没有任何问题」的表）",
              f"停在第 {st['currentStep']} 段 / 出错的第一段是 {first_bad}")
        check("至少选一项" in page.evaluate("() => document.body.innerText"),
              "错误文案说清了要做什么")
        wipe_applications()
        ctx.close()

        # ---------------- 没有 JS：三段全展开 ----------------
        print("\n分步脚本加载失败（表单必须照常可用）")
        ctx = browser.new_context(viewport=vp)
        do_login(ctx, base, f"{user}:{password}")
        page = ctx.new_page()
        # 拦的是分步脚本本体。它在 Task 13 从 recruit-apply.js 改名成通用的
        # form-enhance.js（注册表单共用同一份）—— 拦错文件这条断言就会假通过。
        page.route("**/js/form-enhance*.js", lambda r: r.fulfill(status=404, body=""))
        page.goto(base + URL, wait_until="load")
        page.wait_for_timeout(600)
        st = page.evaluate(PANEL)
        check(st["hasForm"] and not st["stepped"], "脚本没接管")
        check(st["visibleSteps"] == 5, "五段全部展开", f"可见 {st['visibleSteps']} 段")
        check(st["submitHidden"] is False, "提交按钮可用（没有 JS 也能交）")
        # 没有 JS 时多选组照样能填、也照样有名字（组名来自 legend，不依赖脚本）
        check(all(g["groupName"] for g in st["groups"]),
              "没有 JS 时多选组仍然有组名", str([g["groupName"] for g in st["groups"]]))
        ctx.close()

        # ---------------- 已报名：进度时间线 ----------------
        print("\n已报名（进度时间线）")
        from recruitment.models import Application

        from django.contrib.auth import get_user_model

        who = get_user_model().objects.get(username=user)
        # 纸质申请表那几项也要填上。**种成空的等于没种**：后面几条断言看的是
        # 进度时间线，而这条记录同时也是驾驶舱详情页与分布统计的样本 —— 全是
        # 「未填」的话那两页有没有接对压根验不出来。
        app = Application.objects.create(
            campaign=campaign, user=who, department=Application.Department.HARDWARE,
            self_intro="自动化测试提交的自我介绍。",
            interests=[Application.Interest.MCU, Application.Interest.OTHER],
            interests_other="电机控制",
            skills="焊过几块板子",
            first_impression="在实验室门口看过一墙作品。",
            motto="想做出一台自己的示波器。",
            heard_from=[Application.Channel.SENIOR, Application.Channel.ONLINE],
        )
        ctx, page = open_page()
        st = page.evaluate(PANEL)
        check(not st["hasForm"], "已报名后不再显示空表单")
        check(st["track"] == [True, False, False],
              "刚报名：只有第一个焊盘通电", str(st["track"]))
        check(st["leadStat"] == "1", "实时数据变成 1 人已报名", st["leadStat"])

        app.status = Application.Status.FIRST_PASS
        app.save(update_fields=["status"])
        page.reload(wait_until="load")
        page.wait_for_timeout(300)
        st = page.evaluate(PANEL)
        check(st["track"] == [True, True, False],
              "一面通过：前两个焊盘通电", str(st["track"]))

        app.status = Application.Status.SECOND_PASS
        app.save(update_fields=["status"])
        page.reload(wait_until="load")
        page.wait_for_timeout(300)
        st = page.evaluate(PANEL)
        check(st["track"] == [True, True, True], "二面通过：全部通电", str(st["track"]))
        page.screenshot(path=str(SHOTS / "recruitment-track.png"))

        # 未录取是终止态，不是第四个节点
        app.status = Application.Status.REJECTED
        app.save(update_fields=["status"])
        page.reload(wait_until="load")
        page.wait_for_timeout(300)
        st = page.evaluate(PANEL)
        check(len(st["track"]) == 3, "未录取没有变成第四个节点", f"{len(st['track'])} 个节点")
        check("未录取" in st["text"], "单独说明了未录取，并且给了下一步")
        ctx.close()

        # ---------------- 已是会员 ----------------
        print("\n已是科协会员")
        wipe_applications()
        set_level(3)
        ctx, page = open_page()
        st = page.evaluate(PANEL)
        check("会员" in st["heading"], "右栏是「你已经是科协会员」", st["heading"].strip())
        check(not st["hasForm"], "不再给报名表")
        ctx.close()

        # ---------------- 已关闭 ----------------
        print("\n本批次已关闭")
        from django.utils import timezone

        set_level(1)
        campaign.closes_at = timezone.now() - timezone.timedelta(hours=1)
        campaign.save(update_fields=["closes_at"])
        ctx, page = open_page()
        st = page.evaluate(PANEL)
        check(not st["hasForm"], "关闭后不给报名表")
        check("不收报名" in st["heading"] or "关闭" in st["heading"],
              "右栏说明已关闭", st["heading"].strip())
        ctx.close()

        # ---------------- 连批次都没有 ----------------
        print("\n没有任何启用的批次")
        from recruitment.models import Campaign

        Campaign.objects.update(is_active=False)
        ctx, page = open_page()
        st = page.evaluate(PANEL)
        check("关闭" in st["heroTitle"], "Hero 直接说通道关闭", st["heroTitle"].strip())
        check(st["heading"] == "(no panel)", "整块报名区不渲染")
        ctx.close()

        browser.close()

    # 收尾：把开发库恢复成「有一个进行中的批次 + 站务账号」
    open_campaign()
    wipe_applications()
    set_level(4)

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("招新落地页契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
