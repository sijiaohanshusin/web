# -*- coding: utf-8 -*-
"""校验首页分镜 00「开场」/ 02「数据」/ 03「方向」/ 06「路线」/ 10「加入」。

这些段落的价值全在**时序与状态推进**上，而它们是静态截图看不出来的：

  - 分镜 00：加载动画的幕布揭开，巨字才开始逐行升起。真实踩过 —— 这些动画的
    延迟最迟 .8s、时长 1.1s，到 1.9s 就全跑完了，而加载动画那时才刚到 85%，
    于是幕布升起时文字早已就位，「揭幕接 Hero」这一拍完全是空的。截图上一切
    正常，只有把时间轴摊开才看得见。
  - 分镜 02：扫描线扫过之后大数字才定格。如果数字自己用另一个
    IntersectionObserver 触发（阈值还不一样），慢慢滚和快速滚会看到不同的顺序。
  - 分镜 06：电流沿 PCB 走线推进，经过哪个焊盘点亮哪个。焊盘位置是实测出来的，
    栅格一改就可能全部错位 —— 只有真的滚一遍才知道有没有按顺序亮。
  - 分镜 10：倒计时是渐进增强的（静态日期永远在，滴答的时钟是 JS 加的），
    要证明「脚本在时时钟真的在走」和「脚本不在时不会露出一排 --」。

顺带钉住区块之间的过渡件（`includes/edge.html` 那排邮票孔）：它的方向参数
`from` 指的是**上一个**区块的明暗，写反的话孔和自己这块同色、整条看不见，
而且不报错、截图上和「本来就没加」长得一样。

跑法：python scripts/check_hero.py
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

from shoot import PORT, DevServer  # noqa: E402

SHOTS = REPO / ".shots"
failures = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


HERO_STATE = """
() => {
    const line = document.querySelector('.nf-hero-title .line-reveal');
    const scan = document.querySelector('.nf-hero-scan');
    if (!line) return null;
    const cs = getComputedStyle(line);
    return {
        locked: document.documentElement.classList.contains('esta-pre-lock'),
        playState: cs.animationPlayState,
        opacity: parseFloat(cs.opacity),
        scanDisplay: scan ? getComputedStyle(scan).display : 'missing',
        scanPlay: scan ? getComputedStyle(scan).animationPlayState : '',
        scanName: scan ? getComputedStyle(scan).animationName : '',
    };
}
"""

DATA_STATE = """
() => {
    const sec = document.querySelector('.nf-bignum-section');
    const big = document.querySelector('.nf-bignum');
    const num = document.querySelector('.nf-bignum .counter');
    if (!sec || !num) return null;
    const secCs = getComputedStyle(sec);
    return {
        hasScope: sec.classList.contains('nf-scope'),
        gridLayers: (secCs.backgroundImage.match(/linear-gradient/g) || []).length,
        visible: big.classList.contains('is-visible'),
        sweepName: getComputedStyle(big, '::after').animationName,
        text: num.textContent.trim(),
        target: num.getAttribute('data-target'),
        delay: num.getAttribute('data-delay'),
    };
}
"""

# 时序埋点。断言「数字在扫描线之后才动」不能靠「某个时刻去看它是不是还是 0」——
# 采样点早一点晚一点结论就反了（实测滚动过程中区块已经可见，820ms 延迟早走完）。
# 改成记录两个事件的时间戳，比它们的差值。
MARKS = """
window.__marks = {};
document.addEventListener('DOMContentLoaded', function () {
    var big = document.querySelector('.nf-bignum');
    var num = big && big.querySelector('.counter');
    if (!big || !num) return;
    new MutationObserver(function () {
        if (!window.__marks.visible && big.classList.contains('is-visible')) {
            window.__marks.visible = performance.now();
        }
    }).observe(big, { attributes: true, attributeFilter: ['class'] });
    new MutationObserver(function () {
        if (!window.__marks.counted && num.textContent.trim() !== '0') {
            window.__marks.counted = performance.now();
        }
    }).observe(num, { childList: true, characterData: true, subtree: true });
});
"""

SCROLL_TO = """
(sel) => {
    const el = document.querySelector(sel);
    const y = Math.round(el.getBoundingClientRect().top + window.scrollY - 80);
    const l = window.ESTA && window.ESTA.motion && window.ESTA.motion.lenis;
    if (l) l.scrollTo(y, { immediate: true }); else window.scrollTo(0, y);
}
"""

# 绝对像素定位。分镜 06 要看「电流推进到一半」的中间态，靠 --scroll-to 那种
# 「把元素顶到视口顶部」是做不到的（那时进度已经算满了）。
SCROLL_ABS = """
(y) => {
    const l = window.ESTA && window.ESTA.motion && window.ESTA.motion.lenis;
    if (l) l.scrollTo(y, { immediate: true }); else window.scrollTo(0, y);
}
"""

DIR_STATE = """
() => [...document.querySelectorAll('.nf-dir-card')].map(card => {
    const sym = card.querySelector('.nf-dir-sym .icon');
    const first = sym && sym.firstElementChild;
    return {
        hasSym: !!sym,
        // 静止态必须是画好的，不能默认残缺
        dashoffset: first ? getComputedStyle(first).strokeDashoffset : '',
        paths: sym ? sym.children.length : 0,
    };
})
"""

ROADMAP_STATE = """
() => {
    const line = document.querySelector('.nf-tl-line');
    const bar = document.getElementById('nf-tl-progress');
    if (!line || !bar) return null;
    return {
        width: parseFloat(bar.style.width) || 0,
        trunkColor: getComputedStyle(line).backgroundColor,
        live: [...document.querySelectorAll('.nf-tl-num')]
            .map(p => p.classList.contains('is-live')),
    };
}
"""

# 区块过渡件（邮票孔）。这条断言存在的唯一理由：**方向写反是静默的。**
# 孔的颜色取自上一个区块的底色，写反了就和自己这块同色 —— 整条看不见，
# 而 HTML 照常渲染、控制台干净、截图上也只是「这里没有过渡件」，
# 而「本来就没有」和「写反了」在图上长得一模一样。
#
# 所以判据是关系而不是字面值：孔色 == 上一个 section 的底色，且 != 自己的底色。
# 底色要**逐层向上找不透明背景**（section 自己可能是透明的），拿 rgb() 比。
EDGE_STATE = """
() => {
    const norm = (c) => (c || '').replace(/\\s+/g, '');
    const opaqueBg = (el) => {
        let n = el;
        while (n) {
            const m = getComputedStyle(n).backgroundColor
                .match(/rgba?\\(([^)]+)\\)/);
            if (m) {
                const v = m[1].split(/[,\\s/]+/).filter(Boolean).map(Number);
                const a = v.length > 3 ? v[3] : 1;
                if (a > 0.99) return `rgb(${v[0]}, ${v[1]}, ${v[2]})`;
            }
            n = n.parentElement;
        }
        return null;
    };
    const name = (el) => el && (el.id || (el.className || '').split(' ')
        .filter(c => c.startsWith('nf-') && c !== 'nf-section').join('.') || el.tagName);
    return [...document.querySelectorAll('.edge')].map((el) => {
        const cs = getComputedStyle(el);
        const own = el.closest('section');
        let prev = own ? own.previousElementSibling : null;
        while (prev && prev.tagName !== 'SECTION') prev = prev.previousElementSibling;
        const r = el.getBoundingClientRect();
        const ownR = own ? own.getBoundingClientRect() : null;
        return {
            own: name(own),
            prev: name(prev),
            dir: (el.className.match(/edge-from-[a-z]+/) || [''])[0],
            // 孔色从 computed background-image 里抠，而不是读 --edge-from：
            // 后者就算方向类没生效（比如拼错）也可能继承到一个值，
            // 前者是「渐变里真的用上的那个颜色」。
            hole: norm((cs.backgroundImage.match(/rgba?\\([^)]+\\)/) || [''])[0]),
            ownBg: norm(own ? opaqueBg(own) : ''),
            prevBg: norm(prev ? opaqueBg(prev) : ''),
            h: Math.round(r.height * 10) / 10,
            w: Math.round(r.width),
            // 必须正好压在分界线上，差一点就成了「区块里有一排点」
            dTop: ownR ? Math.round((r.top - ownR.top) * 10) / 10 : null,
            size: cs.backgroundSize,
            repeat: cs.backgroundRepeat,
        };
    });
}
"""

COUNTDOWN_STATE = """
() => {
    const box = document.querySelector('[data-countdown]');
    if (!box) return null;
    const clock = box.querySelector('.nf-countdown-clock');
    const cell = (k) => {
        const el = box.querySelector('[data-cd="' + k + '"]');
        return el ? el.textContent.trim() : '';
    };
    return {
        deadline: box.getAttribute('data-countdown'),
        staticText: (box.querySelector('.nf-countdown-static') || {}).textContent || '',
        clockHidden: clock ? clock.hidden : null,
        clockAriaHidden: clock ? clock.getAttribute('aria-hidden') : null,
        d: cell('d'), h: cell('h'), m: cell('m'), s: cell('s'),
    };
}
"""


def seed_campaign():
    """确保有一个「进行中且有截止时间」的招新批次，否则倒计时根本不渲染。

    必须在 DevServer 起来**之前**做：招新状态在服务端缓存 5 分钟，而 dev 用的是
    进程内 LocMem 缓存，外部脚本没法让它失效。新进程的缓存是冷的，正好读到。
    """
    import django

    django.setup()
    from django.utils import timezone

    from recruitment.models import Campaign

    campaign = Campaign.current()
    deadline = timezone.now() + timezone.timedelta(days=12, hours=5)
    if campaign is None:
        Campaign.objects.create(name="自动化测试批次", is_active=True, closes_at=deadline)
        return "created"
    changed = []
    if not campaign.is_active:
        campaign.is_active = True
        changed.append("is_active")
    if campaign.opens_at > timezone.now():
        campaign.opens_at = timezone.now() - timezone.timedelta(days=1)
        changed.append("opens_at")
    if campaign.closes_at is None or campaign.closes_at <= timezone.now():
        campaign.closes_at = deadline
        changed.append("closes_at")
    if changed:
        campaign.save(update_fields=changed)
    return ",".join(changed) or "already ok"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(exist_ok=True)
    print(f"招新批次：{seed_campaign()}")

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        base = f"http://127.0.0.1:{PORT}/"
        vp = {"width": 1440, "height": 900}

        # ---------------- 分镜 00：揭幕接 Hero ----------------
        print("分镜 00：加载动画揭幕才起跑")
        ctx = browser.new_context(viewport=vp)
        errors = []
        page = ctx.new_page()
        page.add_init_script(MARKS)
        page.on("pageerror", lambda e: errors.append(str(e)))
        # 只等 commit：必须在加载动画还盖着的时候就开始采样。
        # 但**不能**一看到「没有锁」就当成已解锁 —— 页面刚 commit 时样式表和
        # preloader.js 都还没就位，那会儿 html 上一个类都没有，看起来和「已经
        # 解锁」一模一样。必须先等锁真的出现，再采样到它消失。
        page.goto(base, wait_until="commit")
        page.wait_for_function(
            "() => document.documentElement.classList.contains('esta-pre-lock')",
            timeout=15000)

        locked_samples = []
        for _ in range(60):
            st = page.evaluate(HERO_STATE)
            if not st or not st["locked"]:
                break
            locked_samples.append(st)
            page.wait_for_timeout(100)

        check(bool(locked_samples), "抓到了加载动画还盖着的窗口",
              f"{len(locked_samples)} 个采样点")
        if locked_samples:
            check(all(s["playState"] == "paused" for s in locked_samples),
                  "锁期间巨字的动画被按住",
                  ",".join({s["playState"] for s in locked_samples}))
            check(all(s["opacity"] < 0.05 for s in locked_samples),
                  "锁期间巨字确实还看不见",
                  f"最大不透明度 {max(s['opacity'] for s in locked_samples):.2f}")
            check(all(s["scanPlay"] == "paused" for s in locked_samples),
                  "锁期间扫描线也按住")

        # 解锁后应当升起来
        page.wait_for_function(
            "() => !document.documentElement.classList.contains('esta-pre-lock')",
            timeout=20000)
        page.wait_for_timeout(1600)
        st = page.evaluate(HERO_STATE)
        check(st and st["playState"] == "running" or (st and st["opacity"] > 0.95),
              "解锁后动画放行")
        check(st and st["opacity"] > 0.95, "巨字已经完全升起",
              f"不透明度 {(st or {}).get('opacity')}")
        check(st and st["scanName"] == "hero-scan", "扫描线动画在跑",
              (st or {}).get("scanName", ""))
        page.screenshot(path=str(SHOTS / "hero-00.png"))

        # ---------------- 区块过渡件：孔色必须取自上一个区块 ----------------
        print("\n区块过渡件（邮票孔）：方向不能写反")
        edges = page.evaluate(EDGE_STATE)
        # 首页有六处「上下明暗一定相反」的边界加了过渡件，但作品段整块在
        # `{% if featured_works %}` 里 —— 开发库没有精选作品时它压根不渲染，
        # 于是期望值要按 DOM 现场算，不能写死 6（写死的话这条会因为库里没数据
        # 而常红，很快就被当成噪音忽略掉）。
        # 荣誉段与学习资源段刻意没有过渡件：它们的上一个区块是黑还是白取决于
        # 两个 `{% if %}` 的组合，方向没法静态确定（模板里有说明）。
        has_works = page.evaluate("() => !!document.querySelector('#nf-works')")
        expect = 6 if has_works else 5
        check(len(edges) == expect, "每处无条件黑白边界都有过渡件",
              f"{len(edges)} 条 / 期望 {expect}"
              f"（作品段{'渲染了' if has_works else '没渲染，它整块在 if 里'}）")
        for e in edges:
            print(f"     {e['own']:<18} 上接 {str(e['prev']):<18} {e['dir']:<16}"
                  f" 孔 {e['hole']}  自身 {e['ownBg']}  上一块 {e['prevBg']}"
                  f"  顶边偏移 {e['dTop']}")
        check(all(e["prev"] for e in edges), "每条过渡件的上一个区块都找得到")
        check(all(e["hole"] and e["hole"] == e["prevBg"] for e in edges),
              "孔色 == 上一个区块的底色（读起来像从上面掰下来）",
              "; ".join(f"{e['own']}: {e['hole']} vs {e['prevBg']}"
                        for e in edges if e["hole"] != e["prevBg"]) or "全部一致")
        check(all(e["hole"] != e["ownBg"] for e in edges),
              "孔色 != 自身底色（不会整条看不见）",
              "; ".join(f"{e['own']}: {e['hole']}"
                        for e in edges if e["hole"] == e["ownBg"]) or "全部有反差")
        check(all(abs(e["dTop"]) < 1 for e in edges), "每条都压在自己区块的顶边上",
              str([e["dTop"] for e in edges]))
        check(all(e["h"] > 1 and e["w"] > 600 for e in edges),
              "有高度、铺满整宽", f"高 {sorted({e['h'] for e in edges})}")
        check(all(e["repeat"].startswith("repeat") and "px" in e["size"] for e in edges),
              "按孔距横向平铺", "; ".join(sorted({e["size"] for e in edges})))

        # ---------------- 分镜 02：扫描线扫过后定格 ----------------
        print("\n分镜 02：示波器网格 + 扫描线扫过后定格")
        page.evaluate(SCROLL_TO, ".nf-bignum-section")
        page.wait_for_timeout(200)
        early = page.evaluate(DATA_STATE)
        check(early and early["hasScope"], "区块铺了示波器网格")
        check(early and early["gridLayers"] >= 4, "网格是双层（细格 + 粗格）",
              f"{(early or {}).get('gridLayers')} 层渐变")
        check(early and early["delay"], "大数字带了对齐扫描线的延迟",
              f"{(early or {}).get('delay')}ms")

        page.wait_for_timeout(2600)
        marks = page.evaluate("() => window.__marks || {}")
        gap = (marks.get("counted", 0) - marks.get("visible", 0)) if marks.get("counted") else -1
        check(gap >= 600,
              "数字比扫描线晚起跑（扫过之后才定格）",
              f"间隔 {gap:.0f}ms，期望 ≥600ms（延迟设的 820ms）")
        late = page.evaluate(DATA_STATE)
        check(late and late["visible"], "区块已标记可见（扫描线的触发源）")
        check(late and late["sweepName"] == "scan-sweep", "扫描线动画已挂上",
              (late or {}).get("sweepName", ""))
        check(late and late["text"] == late["target"],
              "扫描线扫过后数字定格到目标值",
              f"{(late or {}).get('text')} / 目标 {(late or {}).get('target')}")
        page.screenshot(path=str(SHOTS / "hero-02.png"))

        # ---------------- 分镜 03：元件符号 ----------------
        print("\n分镜 03：三大方向的元件符号")
        page.evaluate(SCROLL_TO, ".nf-dir-grid")
        page.wait_for_timeout(400)
        dirs = page.evaluate(DIR_STATE)
        check(len(dirs) == 3, "三张方向卡", f"{len(dirs)} 张")
        check(all(d["hasSym"] for d in dirs), "每张卡都有元件符号")
        check(all(d["paths"] >= 2 for d in dirs), "符号是多段路径（能做描线）",
              str([d["paths"] for d in dirs]))
        # 静止态必须画好：符号不是「等你 hover 才完整」的东西
        check(all(d["dashoffset"] in ("0px", "0") for d in dirs),
              "静止态描线是完整的（不残缺）", str([d["dashoffset"] for d in dirs]))
        page.screenshot(path=str(SHOTS / "home-03.png"))

        # ---------------- 分镜 06：走线通电 ----------------
        print("\n分镜 06：电流沿走线推进，逐个点亮焊盘")
        anchor = page.evaluate(
            "() => Math.round(document.querySelector('#nf-roadmap')"
            ".getBoundingClientRect().top + window.scrollY)")
        seen = []
        for offset in (-780, -560, -360, -160, 40):
            page.evaluate(SCROLL_ABS, anchor + offset)
            page.wait_for_timeout(320)
            st = page.evaluate(ROADMAP_STATE)
            seen.append((offset, st["width"], st["live"]))
        for offset, width, live in seen:
            print(f"     偏移 {offset:>5}  进度 {width:5.1f}%  点亮 {sum(live)}/{len(live)}")

        widths = [w for _, w, _ in seen]
        check(all(b >= a - 0.01 for a, b in zip(widths, widths[1:])),
              "进度单调不回退", str([round(w, 1) for w in widths]))
        counts = [sum(l) for _, _, l in seen]
        check(all(b >= a for a, b in zip(counts, counts[1:])),
              "点亮的焊盘数单调不回退", str(counts))
        check(counts[0] < counts[-1], "确实推进了（首尾点亮数不同）",
              f"{counts[0]} → {counts[-1]}")
        check(counts[-1] == len(seen[-1][2]), "走到底时全部点亮",
              f"{counts[-1]}/{len(seen[-1][2])}")
        # 点亮必须是从左到右的前缀，不能跳着亮
        for offset, _, live in seen:
            prefix = live == sorted(live, reverse=True)
            if not prefix:
                check(False, f"偏移 {offset} 处点亮是连续前缀", str(live))
                break
        else:
            check(True, "任何时刻点亮的都是从左数的连续几个（不跳亮）")
        page.screenshot(path=str(SHOTS / "home-06.png"))

        # ---------------- 分镜 10：倒计时 ----------------
        print("\n分镜 10：招新截止倒计时")
        page.evaluate(SCROLL_TO, "#join")
        page.wait_for_timeout(400)
        cd = page.evaluate(COUNTDOWN_STATE)
        check(cd is not None, "倒计时已渲染（有进行中的批次且设了截止时间）")
        if cd:
            check("报名截止" in cd["staticText"], "静态截止日期在（无障碍树里的权威信息）",
                  cd["staticText"].strip()[:40])
            check(cd["clockHidden"] is False, "JS 把时钟放出来了")
            check(cd["clockAriaHidden"] == "true",
                  "时钟对读屏软件隐藏（每秒变一次是噪音）")
            check(cd["d"].isdigit() and cd["s"].isdigit(),
                  "时钟填上了数字", f"{cd['d']}天 {cd['h']}:{cd['m']}:{cd['s']}")
            before = cd["s"]
            page.wait_for_timeout(1500)
            after = page.evaluate(COUNTDOWN_STATE)["s"]
            check(before != after, "秒位在走", f"{before} → {after}")
        page.screenshot(path=str(SHOTS / "home-10.png"))

        check(not errors, "无未捕获异常", "; ".join(errors[:2]))
        ctx.close()

        # ---------------- 倒计时：脚本挂了也不能露出 "--" ----------------
        # 拦的是 site.js：倒计时在 Task 12 从 home.js 搬到了 site.js（招新落地页
        # 也要用同一份实现）。这条断言曾经因为拦错文件而假通过 —— 拦 home.js 时
        # 倒计时照样跑起来，"脚本挂了" 的场景根本没被模拟到。改这里之前先确认
        # nf-countdown 的实现到底在哪个文件。
        print("\n倒计时脚本加载失败（静态日期必须还在）")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        page.route("**/js/site*.js", lambda r: r.fulfill(status=404, body=""))
        page.goto(base, wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        cd = page.evaluate(COUNTDOWN_STATE)
        check(cd and "报名截止" in cd["staticText"], "静态截止日期照常显示")
        check(cd and cd["clockHidden"] is True, "时钟保持隐藏，不露出一排 --")
        ctx.close()

        # ---------------- reduced-motion ----------------
        print("\nprefers-reduced-motion")
        ctx = browser.new_context(viewport=vp, reduced_motion="reduce")
        page = ctx.new_page()
        page.goto(base, wait_until="load")
        page.wait_for_timeout(600)
        st = page.evaluate(HERO_STATE)
        check(st and st["scanDisplay"] == "none", "不显示扫描线",
              (st or {}).get("scanDisplay", ""))
        check(st and st["opacity"] > 0.95, "巨字直接可见（不做入场动画）")
        page.evaluate(SCROLL_TO, ".nf-bignum-section")
        page.wait_for_timeout(500)
        d = page.evaluate(DATA_STATE)
        check(d and d["text"] == d["target"], "数字直接是终值（信息不丢）",
              f"{(d or {}).get('text')} / {(d or {}).get('target')}")
        ctx.close()

        browser.close()

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("首页分镜 00 / 02 / 03 / 06 / 10 与区块过渡件契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
