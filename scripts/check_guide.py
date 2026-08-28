# -*- coding: utf-8 -*-
"""校验新生指南的长页阅读体验。

这一页是全站最长的一页，它的风险和别的页面不一样：

  1. **目录通电必须是「前缀」语义** —— 读到第 3 章时 1/2/3 都该亮着。这一条
     很容易写成 IntersectionObserver（「谁现在可见谁就亮」），那样长章节滚过去
     之后会把已读的章节又熄掉，读者以为自己退回去了。只有真的滚一遍才看得出来。
  2. **进度线要跟得上文档高度的变化**。这一页有 10 个折叠块，展开一个文档就长
     一大截；如果只在 scroll 时算，展开后进度线会停在一个错误的比例上。
  3. **69 张静态图**。任何一个文件名拼错，线上就是一个碎图图标，而模板渲染
     不会报错。所以要断言「没有失败请求」。
  4. 脚本挂了要退化成一份**可用的锚点目录**，不能只剩一列光秃秃的数字。

跑法：python scripts/check_guide.py
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
URL = "/recruit/"
failures = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def settle(page, tries: int = 20) -> int:
    """等滚动停下来再断言。

    `html { scroll-behavior: smooth }` 让锚点跳转变成一段动画，跨 4800px 要一秒
    多。固定 `wait_for_timeout(500)` 会在半路上采样，读到一个「跳歪了」的位置 ——
    实测过一次，看着像 Lenis 和原生锚点打架，其实只是没走完。
    """
    last = None
    for _ in range(tries):
        page.wait_for_timeout(120)
        now = page.evaluate("() => Math.round(window.scrollY)")
        if now == last:
            return now
        last = now
    return last or 0


STATE = """
() => {
    const toc = document.getElementById('recruit-toc');
    const links = [...toc.querySelectorAll('a')];
    const fill = document.getElementById('rg-bar-fill');
    const trunk = document.querySelector('.rg-trunk');
    const tocTop = toc.getBoundingClientRect().top;
    const padCenter = (a) => {
        const p = a.querySelector('.rg-pad');
        const b = p.getBoundingClientRect();
        return b.top + b.height / 2 - tocTop;
    };
    return {
        read: links.map(a => a.classList.contains('is-read')),
        current: links.findIndex(a => a.classList.contains('is-current')),
        bar: parseFloat(fill ? fill.style.width : '0') || 0,
        trunkTop: trunk ? parseFloat(trunk.style.top) || 0 : -1,
        trunkH: trunk ? parseFloat(trunk.style.height) || 0 : -1,
        padCenters: links.map(padCenter),
        nos: [...document.querySelectorAll('.recruit-content .rg-no')]
            .map(e => e.textContent.trim()),
        pads: links.map(a => (a.querySelector('.rg-pad') || {}).textContent),
        docH: document.documentElement.scrollHeight,
    };
}
"""

SCROLL_TO_SECTION = """
(id) => {
    const el = document.getElementById(id);
    const y = Math.round(el.getBoundingClientRect().top + window.scrollY - 90);
    const l = window.ESTA && window.ESTA.motion && window.ESTA.motion.lenis;
    if (l) l.scrollTo(y, { immediate: true }); else window.scrollTo(0, y);
}
"""

SLOTS = """
() => [...document.querySelectorAll('.rg-shot')].map(el => ({
    key: el.getAttribute('data-slot-key'),
    empty: el.classList.contains('is-empty'),
    fids: el.querySelectorAll('.slot-fid').length,
    label: (el.querySelector('.slot-empty-label') || {}).textContent || '',
    brief: (el.querySelector('.slot-empty-brief') || {}).textContent || '',
    ratio: el.style.aspectRatio || getComputedStyle(el).aspectRatio,
}))
"""

MOBILE = """
() => {
    const nav = document.querySelector('.site-nav');
    const toc = document.getElementById('recruit-toc');
    const first = toc.querySelector('a');
    const content = document.querySelector('.recruit-content');
    const cs = getComputedStyle(toc);
    return {
        vw: window.innerWidth,
        navBottom: Math.round(nav.getBoundingClientRect().bottom),
        tocTop: Math.round(toc.getBoundingClientRect().top),
        tocDisplay: cs.display,
        tocPosition: cs.position,
        // 药丸行：第一项不该占满整行宽
        firstW: Math.round(first.getBoundingClientRect().width),
        contentW: Math.round(content.getBoundingClientRect().width),
        docW: document.documentElement.scrollWidth,
        trunkShown: getComputedStyle(document.querySelector('.rg-trunk')).display,
    };
}
"""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(exist_ok=True)

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        base = f"http://127.0.0.1:{PORT}"
        vp = {"width": 1440, "height": 900}

        # ---------------- 完整能力 ----------------
        print("目录通电：读过的章节保持点亮（前缀语义）")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        errors, failed = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed",
                lambda r: failed.append(f"{r.url} {(r.failure or '')}"))
        page.on("response",
                lambda r: failed.append(f"{r.url} HTTP {r.status}") if r.status >= 400 else None)
        page.goto(base + URL, wait_until="load")
        page.wait_for_timeout(700)

        st = page.evaluate(STATE)
        check(st["pads"] == ["01", "02", "03", "04", "05"],
              "目录五章都带丝印编号", str(st["pads"]))
        check(st["nos"] == ["01", "02", "03", "04", "05"],
              "正文标题的编号与目录一一对应", str(st["nos"]))
        check(st["read"] == [True, False, False, False, False],
              "刚进页面只有第一章通电", str(st["read"]))

        seen = []
        for sid in ("intro", "training", "hardware", "software", "resources"):
            page.evaluate(SCROLL_TO_SECTION, sid)
            page.wait_for_timeout(320)
            s = page.evaluate(STATE)
            seen.append((sid, sum(s["read"]), s["current"], s["bar"]))
        for sid, n, cur, bar in seen:
            print(f"     #{sid:<10} 通电 {n}/5  当前 {cur}  进度 {bar:5.1f}%")

        counts = [n for _, n, _, _ in seen]
        check(all(b >= a for a, b in zip(counts, counts[1:])),
              "通电数单调不回退（读过的不会又熄掉）", str(counts))
        check(counts[-1] == 5, "走到最后一章时全部通电", f"{counts[-1]}/5")
        currents = [c for _, _, c, _ in seen]
        check(currents == sorted(currents), "当前章节随滚动前进不乱跳", str(currents))
        bars = [b for _, _, _, b in seen]
        check(all(b >= a - 0.01 for a, b in zip(bars, bars[1:])),
              "阅读进度单调不回退", str([round(b, 1) for b in bars]))

        # 任何时刻点亮的必须是从上往下的连续前缀
        s = page.evaluate(STATE)
        check(s["read"] == sorted(s["read"], reverse=True),
              "点亮的是从第一章数的连续几章（不跳亮）", str(s["read"]))

        # 主干必须落在首末焊盘中心之间
        first_c, cur_c = s["padCenters"][0], s["padCenters"][s["current"]]
        check(abs(s["trunkTop"] - first_c) < 3,
              "主干从第一个焊盘中心起（不在上方悬空）",
              f"top={s['trunkTop']:.0f} 焊盘中心={first_c:.0f}")
        check(abs(s["trunkTop"] + s["trunkH"] - cur_c) < 3,
              "主干止于当前焊盘中心（不越过）",
              f"末端={s['trunkTop'] + s['trunkH']:.0f} 焊盘中心={cur_c:.0f}")

        # 滚到底进度线应当接近满
        page.evaluate("() => { const l = window.ESTA && window.ESTA.motion && window.ESTA.motion.lenis;"
                      " const y = document.documentElement.scrollHeight;"
                      " if (l) l.scrollTo(y, { immediate: true }); else window.scrollTo(0, y); }")
        page.wait_for_timeout(350)
        s = page.evaluate(STATE)
        check(s["bar"] > 97, "滚到底进度线接近 100%", f"{s['bar']:.1f}%")
        page.screenshot(path=str(SHOTS / "guide-toc.png"))

        # ---------------- 折叠块改变文档高度 ----------------
        print("\n展开折叠块后进度线要重算（文档变高了）")
        page.evaluate(SCROLL_TO_SECTION, "hardware")
        page.wait_for_timeout(300)
        before = page.evaluate(STATE)
        page.evaluate("""() => {
            const d = [...document.querySelectorAll('details.fold')].find(x => !x.open);
            if (d) d.open = true;
        }""")
        page.wait_for_timeout(800)
        after = page.evaluate(STATE)
        check(after["docH"] > before["docH"], "文档确实变高了",
              f"{before['docH']} → {after['docH']}")
        # **不要写成「比例应该变小」**：如果脚本压根没重算，比例也不会变，那条
        # 断言就永远是绿的（写过一次，实测前后都是 38.6%，看不出任何问题）。
        # 正确的做法是拿 DOM 里的值和现场重新算一遍的值比 —— 没重算就必然不等。
        expected = page.evaluate("""() => {
            const doc = document.documentElement;
            const max = doc.scrollHeight - window.innerHeight;
            return max > 0 ? window.scrollY / max * 100 : 0;
        }""")
        check(abs(after["bar"] - expected) < 0.5,
              "进度线与当前文档高度一致（不是停在展开前的旧值）",
              f"DOM {after['bar']:.2f}% / 现算 {expected:.2f}%")

        # ---------------- 目录锚点 ----------------
        print("\n目录点击真的跳到那一章")
        page.click('#recruit-toc a[href="#software"]')
        settle(page)
        top = page.evaluate(
            "() => Math.round(document.getElementById('software').getBoundingClientRect().top)")
        # 断言的是 scroll-margin-top 的值：没有它，固定导航（74px 高）会把章节
        # 标题盖掉 —— 跳过去正好看不见你要看的那一行。
        check(90 <= top <= 110, "章节标题停在导航下方（scroll-margin-top 生效）",
              f"章节顶 {top}，期望 ≈100")

        check(not errors, "无未捕获异常", "; ".join(errors[:2]))
        check(not failed, f"69 张静态图与全部资源都可达", "; ".join(failed[:3]))
        ctx.close()

        # ---------------- 现场照素材槽 ----------------
        print("\n每章一张现场照（素材槽，拍到之前是空焊盘）")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        page.goto(base + URL, wait_until="load")
        page.wait_for_timeout(500)
        shots = page.evaluate(SLOTS)
        check(len(shots) == 3, "三章各有一个现场照槽位", f"{len(shots)} 个")
        for sh in shots:
            check(sh["fids"] == 4, f"{sh['key']} 有四角定位标", f"{sh['fids']} 个")
            check(bool(sh["label"].strip()), f"{sh['key']} 显示了槽位名称")
            check(len(sh["brief"].strip()) > 8, f"{sh['key']} 显示了拍摄要求")
            check("16" in (sh["ratio"] or ""), f"{sh['key']} 写了比例占住版面",
                  sh["ratio"] or "")
        ctx.close()

        # ---------------- 脚本挂了 ----------------
        print("\nrecruit-guide.js 加载失败（目录必须还能用）")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        page.route("**/js/recruit-guide*.js", lambda r: r.fulfill(status=404, body=""))
        page.goto(base + URL, wait_until="load")
        page.wait_for_timeout(600)
        st = page.evaluate(STATE)
        check(st["pads"] == ["01", "02", "03", "04", "05"], "编号还在（服务端渲染的）")
        check(st["bar"] == 0, "进度线保持 0 宽，不留残迹", f"{st['bar']}%")
        check(sum(st["read"]) == 0, "没有任何焊盘被点亮（没有假状态）")
        page.click('#recruit-toc a[href="#resources"]')
        settle(page)
        top = page.evaluate(
            "() => Math.round(document.getElementById('resources').getBoundingClientRect().top)")
        check(90 <= top <= 110, "目录仍是可用的锚点（纯 HTML 跳转）", f"章节顶 {top}")
        ctx.close()

        # ---------------- 移动端 ----------------
        print("\n移动端（竖走线换成横向药丸行）")
        ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                  is_mobile=True, has_touch=True,
                                  device_scale_factor=2)
        page = ctx.new_page()
        merrs = []
        page.on("pageerror", lambda e: merrs.append(str(e)))
        page.goto(base + URL, wait_until="load")
        page.wait_for_timeout(700)
        m = page.evaluate(MOBILE)
        check(m["tocDisplay"] == "flex" and m["tocPosition"] == "static",
              "目录换成横向药丸行（不再 sticky 占一列）",
              f"{m['tocDisplay']} / {m['tocPosition']}")
        check(m["trunkShown"] == "none", "竖走线在窄屏收掉", m["trunkShown"])
        check(m["firstW"] < m["vw"] * 0.6, "药丸不占满整行（一行能放下多个）",
              f"首项 {m['firstW']} / 视口 {m['vw']}")
        check(m["tocTop"] >= m["navBottom"] - 1, "目录没有被固定导航切掉",
              f"目录顶 {m['tocTop']} / 导航底 {m['navBottom']}")
        check(m["docW"] <= m["vw"] + 1, "没有横向溢出",
              f"文档宽 {m['docW']} / 视口 {m['vw']}")
        check(not merrs, "移动端无未捕获异常", "; ".join(merrs[:2]))
        page.screenshot(path=str(SHOTS / "guide-mobile.png"))
        ctx.close()

        # ---------------- reduced-motion ----------------
        print("\nprefers-reduced-motion")
        ctx = browser.new_context(viewport=vp, reduced_motion="reduce")
        page = ctx.new_page()
        page.goto(base + URL, wait_until="load")
        page.wait_for_timeout(500)
        trans = page.evaluate(
            "() => [getComputedStyle(document.querySelector('.rg-trunk')).transitionDuration,"
            " getComputedStyle(document.querySelector('.rg-pad')).transitionDuration]")
        # 逐个分量判 0s：transitionDuration 是个逗号列表，长度随属性数量变，
        # 写死成 "0s, 0s, 0s, 0s" 这种字面量改一次 CSS 就假失败
        flat = [part.strip() for t in trans for part in t.split(",")]
        check(flat and all(part == "0s" for part in flat),
              "走线与焊盘不做过渡", str(trans))
        st = page.evaluate(STATE)
        check(st["read"][0] is True, "状态信息照常给出（不因减动效丢失）")
        ctx.close()

        browser.close()

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("新生指南契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
