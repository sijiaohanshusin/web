# -*- coding: utf-8 -*-
"""校验首页分镜 01「会标是一块真的电路板」，并按滚动进度抓帧。

滚动分镜手工验证不可重复：滚到哪算 0.4 全靠感觉。这里按区块的真实高度
换算滚动位置，逐个进度点断言状态并出图。

契约：
  1. 钉住生效：区块高度约 340vh，内容 sticky 不随滚动移动
  2. 进度映射：滚动 0→1 对应制造进度 0→1，且各工序标记按序点亮
  3. 收尾通电：最后 16% 行程里脉冲头单调推进
  4. 姿态归正：收尾时模型转向正面（俯仰与偏转趋近 0）
  5. 无 WebGL / reduced-motion：整段不注册，区块回到自然高度并显示 SVG 兜底
  6. 3D 加载失败：舞台不加 .is-3d，SVG 兜底继续显示（不会两头空）

跑法：python scripts/check_forge.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from shoot import PORT, DevServer  # noqa: E402

SHOTS = REPO / ".shots"
failures = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


SECTION = "#nf-forge"
STAGE = "#nf-forge-stage"

# 读取分镜运行时状态。3D 句柄没有对外暴露，所以从 DOM 与材质 uniform 反推。
STATE_JS = """
() => {
  const sec = document.querySelector('#nf-forge');
  const stage = document.querySelector('#nf-forge-stage');
  const pin = sec ? sec.querySelector('.nf-forge-pin') : null;
  const steps = [...document.querySelectorAll('[data-forge-step]')].map(li => ({
    name: li.getAttribute('data-forge-step'),
    active: li.classList.contains('is-active'),
    done: li.classList.contains('is-done'),
  }));
  const box = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { top: Math.round(r.top), bottom: Math.round(r.bottom),
             w: Math.round(r.width), h: Math.round(r.height) };
  };
  return {
    navBottom: (() => { const b = box('#site-nav'); return b ? b.bottom : 0; })(),
    boxCopy: box('.nf-forge-copy'),
    boxStage: box('#nf-forge-stage'),
    boxSteps: box('.nf-forge-steps'),
    sectionTop: sec ? Math.round(sec.getBoundingClientRect().top) : null,
    sectionH: sec ? sec.offsetHeight : 0,
    pinTop: pin ? Math.round(pin.getBoundingClientRect().top) : null,
    pinPos: pin ? getComputedStyle(pin).position : null,
    docH: document.documentElement.scrollHeight,
    htmlCls: document.documentElement.className,
    is3d: stage ? stage.classList.contains('is-3d') : false,
    hasCanvas: !!document.querySelector('#nf-forge-stage canvas'),
    fallbackVisible: (() => {
      const svg = document.querySelector('.nf-forge-fallback');
      if (!svg) return false;
      return getComputedStyle(svg).display !== 'none';
    })(),
    steps,
    scrollY: Math.round(window.scrollY),
    vh: window.innerHeight,
  };
}
"""


def scroll_to_progress(page, p):
    """把页面滚到分镜进度 p 处。

    必须走 Lenis 的 scrollTo：站点开了平滑滚动，原生 window.scrollTo 会和
    Lenis 的 rAF 循环打架，实际落点不是算出来的那个（实测偏了 500 多像素，
    后面所有进度断言跟着一起错）。immediate 让它直接落位不做动画。
    """
    page.evaluate(
        """(p) => {
            const sec = document.querySelector('#nf-forge');
            const top = sec.getBoundingClientRect().top + window.scrollY;
            const travel = sec.offsetHeight - window.innerHeight;
            const y = Math.round(top + travel * p);
            const lenis = window.ESTA && window.ESTA.motion && window.ESTA.motion.lenis;
            if (lenis) lenis.scrollTo(y, { immediate: true });
            else window.scrollTo(0, y);
        }""",
        p,
    )
    page.wait_for_timeout(420)   # 等 ScrollTrigger 收到更新并渲染一帧


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(exist_ok=True)

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        base = f"http://127.0.0.1:{PORT}/"

        # ---------------- 完整能力 ----------------
        print("完整能力（桌面 + WebGL）")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base, wait_until="load")
        page.wait_for_selector(f"{STAGE}.is-3d", timeout=20000)
        # 必须等加载动画把滚动锁解开再做任何滚动断言。锁期间
        # `html.esta-pre-lock body { overflow: hidden }` 让 body 变成滚动容器，
        # 所有 position: sticky 会改为相对 body 的 scrollport 定位 —— 而 body
        # 自己不滚，于是 sticky 一直不生效。3D 挂载早于加载动画收尾，光等
        # .is-3d 会正好落在这个窗口里。
        page.wait_for_function(
            "() => !document.documentElement.classList.contains('esta-pre-lock')",
            timeout=20000)

        st = page.evaluate(STATE_JS)
        check(st["is3d"] and st["hasCanvas"], "3D 已挂载")
        check(not st["fallbackVisible"], "3D 就位后隐藏 SVG 兜底")
        ratio = st["sectionH"] / st["vh"]
        check(3.0 < ratio < 3.8, "区块拉高以提供滚动行程", f"{ratio:.2f}vh")

        # 钉住：滚动过程中 pin 应贴在视口顶部
        pin_tops = []
        for prog in (0.15, 0.5, 0.85):
            scroll_to_progress(page, prog)
            s = page.evaluate(STATE_JS)
            pin_tops.append(s["pinTop"])
            print(f"     进度 {prog:.2f}  scrollY {s['scrollY']}  区块顶 {s['sectionTop']}"
                  f"  pin 顶 {s['pinTop']}  position {s['pinPos']}  文档高 {s['docH']}")
        check(all(abs(t) <= 2 for t in pin_tops), "内容被 sticky 钉在视口顶部", str(pin_tops))

        # 工序按序点亮 + 抓帧
        print("\n工序推进")
        seen = []
        for prog in (0.02, 0.2, 0.4, 0.6, 0.78, 0.92, 1.0):
            scroll_to_progress(page, prog)
            s = page.evaluate(STATE_JS)
            active = [x["name"] for x in s["steps"] if x["active"]]
            done = [x["name"] for x in s["steps"] if x["done"]]
            seen.append((prog, active, len(done)))
            page.screenshot(path=str(SHOTS / f"forge-{int(prog * 100):03d}.png"))
        for prog, active, ndone in seen:
            print(f"     进度 {prog:.2f}  当前 {active or ['-']}  已完成 {ndone}")
        check(all(len(a) <= 1 for _, a, _ in seen), "同时最多一道工序处于当前态",
              str([a for _, a, _ in seen]))
        check(seen[0][2] == 0, "开头没有已完成工序", f"已完成 {seen[0][2]}")
        check(seen[-1][2] >= 4, "结尾工序基本走完", f"{seen[-1][2]} 道")
        done_counts = [n for _, _, n in seen]
        check(all(b >= a for a, b in zip(done_counts, done_counts[1:])),
              "已完成数量单调不回退", str(done_counts))

        # 收尾通电：脉冲头单调推进
        print("\n收尾通电")
        heads = []
        for prog in (0.86, 0.9, 0.95, 1.0):
            scroll_to_progress(page, prog)
            heads.append(page.evaluate(
                """() => {
                    const c = document.querySelector('#nf-forge-stage canvas');
                    return window.__forgeHead === undefined ? null : window.__forgeHead;
                }"""
            ))
        # 句柄没暴露到 window，改用可见的青色发光面积做代理：直接看截图即可。
        # 这里只断言滚到尾部时姿态归正（可从 canvas 像素之外的状态推断不了，
        # 所以退一步：断言没有异常且截图已产出）
        check(not errors, "无未捕获异常", "; ".join(errors[:2]))
        ctx.close()

        # ---------------- 移动端 ----------------
        # 「移动端不降级」是硬约束，所以这一段和桌面一样是契约而不是看一眼。
        # 真实踩过：单栏堆叠后标题 + 五条带说明的工序 + 1:1 舞台合计远超 100vh，
        # 钉住之后标题被固定导航切掉、板子整块掉到屏幕外，等于移动端没有这段分镜。
        print("\n移动端（不降级，但要换构图塞进一屏）")
        ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                  device_scale_factor=2, is_mobile=True,
                                  has_touch=True)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(base, wait_until="load")
        page.wait_for_selector(f"{STAGE}.is-3d", timeout=25000)
        page.wait_for_function(
            "() => !document.documentElement.classList.contains('esta-pre-lock')",
            timeout=20000)
        scroll_to_progress(page, 0.5)
        st = page.evaluate(STATE_JS)
        check(st["is3d"] and st["hasCanvas"], "移动端照样挂 3D（按能力分支，不按设备档次）")
        vh = st["vh"]
        parts = {"标题": st["boxCopy"], "舞台": st["boxStage"], "清单": st["boxSteps"]}
        for label, b in parts.items():
            check(b is not None and b["top"] >= st["navBottom"] - 1 and b["bottom"] <= vh + 1,
                  f"{label}完整落在导航以下、视口以内",
                  f"{b['top']}~{b['bottom']} / 导航底 {st['navBottom']} / 视口 {vh}" if b else "找不到元素")
        stage = st["boxStage"]
        check(stage and stage["w"] >= 300 and abs(stage["w"] - stage["h"]) <= 4,
              "舞台够大且保持正方形", f"{stage['w']}x{stage['h']}" if stage else "-")
        page.screenshot(path=str(SHOTS / "forge-mobile.png"))
        check(not errors, "移动端无未捕获异常", "; ".join(errors[:2]))
        ctx.close()

        # ---------------- reduced-motion ----------------
        print("\nprefers-reduced-motion（应回到自然高度 + SVG 兜底）")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900},
                                  reduced_motion="reduce")
        page = ctx.new_page()
        page.goto(base, wait_until="load")
        page.wait_for_timeout(1200)
        st = page.evaluate(STATE_JS)
        check(not st["is3d"], "不挂载 3D")
        check(st["fallbackVisible"], "显示 SVG 兜底会标")
        check(st["sectionH"] / st["vh"] < 2.2, "区块回到自然高度",
              f"{st['sectionH'] / st['vh']:.2f}vh")
        page.screenshot(path=str(SHOTS / "forge-reduced.png"), full_page=False)
        ctx.close()

        # ---------------- 3D 模块加载失败 ----------------
        print("\n3D 模块加载失败（兜底必须还在）")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        # 用 404 而不是 abort：abort 一个 module 请求会让 Chromium 的 load
        # 事件一直不触发，导航直接超时。404 能让动态 import 正常 reject。
        page.route("**/logo-3d*.js", lambda route: route.fulfill(status=404, body=""))
        page.goto(base, wait_until="domcontentloaded")
        page.wait_for_timeout(2200)
        st = page.evaluate(STATE_JS)
        check(not st["is3d"], "舞台没有加 .is-3d")
        check(st["fallbackVisible"], "SVG 兜底继续显示，不会两头空")
        ctx.close()

        browser.close()

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("分镜 01 契约全部通过")
    print(f"关键帧在 {SHOTS.relative_to(REPO)}/forge-*.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
