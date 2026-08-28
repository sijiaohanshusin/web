# -*- coding: utf-8 -*-
"""校验视频槽的播放决策。

为什么不测「真的播起来了没有」：headless Chromium 通常不带 H.264 解码器，本机也
没有 ffmpeg 可以现造 WebM，真实播放在这个环境里本来就不可靠。而需要守住的东西
其实是**决策逻辑** —— 什么时候该调 play、什么时候绝对不能调。所以这里给
`HTMLMediaElement.prototype.play` 埋点，直接观察 video-slots.js 的判断结果，
不依赖能不能解码。

契约：
  1. 完整能力：进视口就播，离开视口就暂停
  2. prefers-reduced-motion：一次都不播，露出手动播放入口
  3. 省流模式（saveData）：一次都不播，并且把 preload 压到 none（一个字节都不下）
  4. 控制脚本加载失败：<video> 停在封面帧上，页面照常可看（不是白屏）
  5. 手动点播放：能播起来

跑法：python scripts/check_video_slots.py
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
KEY = "home.movie.teaser"
FACADE = "#video-facade"
failures = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


# 埋点必须在页面脚本之前注入，所以走 add_init_script
SPY = """
window.__playCalls = 0;
window.__pauseCalls = 0;
(function () {
    var mp = HTMLMediaElement.prototype;
    var play = mp.play, pause = mp.pause;
    mp.play = function () { window.__playCalls++; try { return play.apply(this, arguments); }
                            catch (e) { return Promise.reject(e); } };
    mp.pause = function () { window.__pauseCalls++; return pause.apply(this, arguments); };
})();
"""

SAVE_DATA = """
Object.defineProperty(navigator, 'connection', {
    value: { saveData: true, effectiveType: '2g' }, configurable: true,
});
"""

STATE = """
() => {
    const fig = document.querySelector('[data-slot-video]');
    if (!fig) return null;
    const v = fig.querySelector('video');
    const b = fig.querySelector('.slot-video-play');
    return {
        plays: window.__playCalls, pauses: window.__pauseCalls,
        paused: v.paused, preload: v.preload,
        poster: v.getAttribute('poster') || '',
        sources: v.querySelectorAll('source').length,
        buttonHidden: b ? b.hidden : null,
    };
}
"""


def seed():
    """给影像区槽位塞一段片子。内容不必能解码 —— 我们只看决策。"""
    import django

    django.setup()
    from core.models import MediaSlot
    from core.tests import make_mp4, make_png

    wipe()
    MediaSlot.objects.create(
        key=KEY, image=make_png("teaser-cover.png", size=(320, 180)),
        alt="片头循环（自动化测试用）", video_mp4=make_mp4("teaser.mp4"),
    )


def wipe():
    from core.models import MediaSlot

    for obj in MediaSlot.objects.filter(key=KEY):
        obj.image.delete(save=False)
        obj.video_mp4.delete(save=False)
        obj.video_webm.delete(save=False)
        obj.delete()


# 站点开了 Lenis 平滑滚动，原生 scrollIntoView / window.scrollTo 会和它的 rAF
# 循环打架，实际落点不是算出来的那个 —— 于是 IntersectionObserver 永远等不到
# 目标进视口。这个坑在分镜 01 的检查脚本里已经踩过一次，这里必须走 Lenis。
SCROLL_TO = """
(sel) => {
    const el = document.querySelector(sel);
    const y = Math.round(el.getBoundingClientRect().top + window.scrollY
                         - (window.innerHeight - el.getBoundingClientRect().height) / 2);
    const lenis = window.ESTA && window.ESTA.motion && window.ESTA.motion.lenis;
    if (lenis) lenis.scrollTo(y, { immediate: true });
    else window.scrollTo(0, y);
}
"""


def open_facade(ctx, base, init_scripts=()):
    page = ctx.new_page()
    for script in (SPY,) + tuple(init_scripts):
        page.add_init_script(script)
    page.goto(base, wait_until="load")
    page.wait_for_function(
        "() => !document.documentElement.classList.contains('esta-pre-lock')",
        timeout=20000)
    page.evaluate(SCROLL_TO, FACADE)
    page.wait_for_timeout(900)
    return page


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(exist_ok=True)
    seed()

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        base = f"http://127.0.0.1:{PORT}/"
        vp = {"width": 1440, "height": 900}

        # ---------------- 1. 完整能力 ----------------
        print("完整能力")
        ctx = browser.new_context(viewport=vp)
        page = open_facade(ctx, base)
        st = page.evaluate(STATE)
        check(st is not None, "影像区渲染成了视频槽")
        check(st and st["sources"] >= 1, "带上了 <source>", f"{(st or {}).get('sources')} 个")
        check(st and st["poster"], "带上了封面帧", (st or {}).get("poster", ""))
        check(st and st["plays"] >= 1, "进视口后尝试播放", f"play 调用 {(st or {}).get('plays')} 次")

        # 滚离视口 → 应当暂停。比的是「离开前后 pause 次数有没有增加」，
        # 不是 pauses >= 1：IntersectionObserver 首次 observe 就会以
        # isIntersecting=false 回调一次，那一次会让 >=1 无条件成立。
        before_pauses = (st or {}).get("pauses", 0)
        page.evaluate("""() => {
            const l = window.ESTA && window.ESTA.motion && window.ESTA.motion.lenis;
            if (l) l.scrollTo(0, { immediate: true }); else window.scrollTo(0, 0);
        }""")
        page.wait_for_timeout(800)
        st2 = page.evaluate(STATE)
        check(st2 and st2["pauses"] > before_pauses, "离开视口后暂停",
              f"pause {before_pauses} → {(st2 or {}).get('pauses')}")
        page.screenshot(path=str(SHOTS / "video-slot-full.png"))
        ctx.close()

        # ---------------- 2. reduced-motion ----------------
        print("\nprefers-reduced-motion（一次都不该播）")
        ctx = browser.new_context(viewport=vp, reduced_motion="reduce")
        page = open_facade(ctx, base)
        st = page.evaluate(STATE)
        check(st and st["plays"] == 0, "没有调用过 play", f"play {(st or {}).get('plays')} 次")
        check(st and st["paused"], "视频处于暂停态（显示封面帧）")
        # 注意断言的是 hidden 属性而不是可见性：facade 里用 CSS 把这颗小按钮
        # 藏掉了（facade 自己那颗大按钮才是入口），但控制器该做的事不变。
        check(st and st["buttonHidden"] is False, "露出了手动播放入口（hidden 已摘）")
        ctx.close()

        # ---------------- 3. 省流模式 ----------------
        print("\n省流模式（saveData）")
        ctx = browser.new_context(viewport=vp)
        page = open_facade(ctx, base, init_scripts=(SAVE_DATA,))
        st = page.evaluate(STATE)
        check(st and st["plays"] == 0, "没有调用过 play", f"play {(st or {}).get('plays')} 次")
        check(st and st["preload"] == "none",
              "preload 压到 none（一个字节的视频都不下）", (st or {}).get("preload", ""))
        check(st and st["buttonHidden"] is False, "露出了手动播放入口")

        # ---------------- 5. 手动点播放 ----------------
        # facade 里这颗按钮被 CSS 藏了，所以用 JS 派发点击而不是 mouse.click
        page.evaluate("""() => document.querySelector('.slot-video-play').click()""")
        page.wait_for_timeout(300)
        st = page.evaluate(STATE)
        check(st and st["plays"] >= 1, "点了手动入口后开始播放",
              f"play {(st or {}).get('plays')} 次")
        check(st and st["buttonHidden"] is True, "播放后收起手动入口")
        ctx.close()

        # ---------------- 4. 控制脚本加载失败 ----------------
        print("\n控制脚本加载失败（内容必须还在）")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        page.add_init_script(SPY)
        page.route("**/video-slots*.js", lambda r: r.fulfill(status=404, body=""))
        page.goto(base, wait_until="load")
        page.evaluate(SCROLL_TO, FACADE)
        page.wait_for_timeout(700)
        st = page.evaluate(STATE)
        check(st is not None, "<video> 仍然在页面上")
        check(st and st["poster"], "封面帧仍然在（不是白屏）")
        check(st and st["paused"], "停在封面帧上，没有异常播放")
        ctx.close()

        browser.close()

    wipe()
    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("视频槽契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
