# -*- coding: utf-8 -*-
"""校验开场加载动画的行为契约，并抓拍关键帧。

加载动画最怕的不是"不好看"，是"把用户永久锁在门外"。所以这里把几条不可
妥协的行为钉死：

  1. 正常路径：进度单调递增 → 揭幕 → 遮罩从 DOM 移除 → 滚动解锁
  2. reduced-motion：整块不出现，也不锁滚动，done 仍然兑现
  3. 同会话二次进入：直接跳过，不再拦一次
  4. preloader.js 加载失败：纯 CSS 兜底仍会在 9 秒内收掉遮罩
  5. 进度不卡顿：不允许长时间停在同一个数字上

跑法：python scripts/check_preloader.py
退出码非 0 表示有契约被破坏。
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from shoot import PORT, DevServer  # noqa: E402  复用同一套开发服务器管理

SHOTS = REPO / ".shots"
BASE = f"http://127.0.0.1:{PORT}"

failures = []


def check(cond, label, detail=""):
    mark = "OK  " if cond else "FAIL"
    print(f"  {mark} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def sample_progress(page, duration_ms=2600, step_ms=100):
    """采样进度读数，返回 [(t, 数值)]。"""
    samples = []
    for i in range(duration_ms // step_ms):
        val = page.evaluate(
            """() => {
                const el = document.getElementById('esta-pre-pct');
                return el ? el.textContent.trim() : null;
            }"""
        )
        samples.append((i * step_ms, val))
        page.wait_for_timeout(step_ms)
    return samples


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(exist_ok=True)

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()

        # ---------------- 1. 正常路径 ----------------
        print("正常路径（桌面，首次访问）")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE, wait_until="domcontentloaded")

        check(page.query_selector("#esta-preloader") is not None, "遮罩已渲染")
        check(
            page.evaluate("() => document.documentElement.classList.contains('esta-pre-lock')"),
            "首帧即锁滚动",
        )

        # 从第一帧就开始采样，完整看到曲线；中途抓一帧描线进行中的画面
        samples = sample_progress(page, duration_ms=800, step_ms=100)
        page.screenshot(path=str(SHOTS / "preloader-mid.png"))
        samples += sample_progress(page, duration_ms=1800, step_ms=100)

        nums = [int(v) for _, v in samples if v and v.isdigit()]
        print("     读数曲线：" + " ".join(str(n) for n in nums))
        check(len(nums) > 8, "读数可采样", f"{len(nums)} 个样本")
        if nums:
            check(all(b >= a for a, b in zip(nums, nums[1:])), "进度单调不倒退",
                  f"{nums[0]} → {nums[-1]}")

            # 只看到达 100 之前的部分：达到 100 之后遮罩还要播 0.9 秒幕布上升
            # 动画才移除，那段读数当然不变，不算停滞。
            ramp = []
            for n in nums:
                ramp.append(n)
                if n >= 100:
                    break
            longest = best = 1
            for a, b in zip(ramp, ramp[1:]):
                best = best + 1 if a == b else 1
                longest = max(longest, best)
            check(longest <= 6, "爬升段无长时间停滞",
                  f"最长连续 {longest} 帧同值（约 {longest * 100}ms），爬升共 {len(ramp)} 帧")

        # 等揭幕
        page.wait_for_function(
            "() => !document.getElementById('esta-preloader')", timeout=9000
        )
        check(True, "遮罩已从 DOM 移除")
        check(
            not page.evaluate("() => document.documentElement.classList.contains('esta-pre-lock')"),
            "滚动已解锁",
        )
        check(
            page.evaluate("() => window.ESTA && !!window.ESTA.preload"),
            "ESTA.preload 契约存在",
        )
        page.evaluate("() => window.scrollTo(0, 400)")
        page.wait_for_timeout(500)
        check(page.evaluate("() => window.scrollY") > 0, "揭幕后可以滚动")
        page.screenshot(path=str(SHOTS / "preloader-after.png"))
        check(not errors, "无未捕获异常", "; ".join(errors[:2]))

        # ---------------- 2. 同会话二次进入 ----------------
        print("\n同会话二次进入（应跳过）")
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(350)
        check(page.query_selector("#esta-preloader") is None, "第二次不再出现遮罩")
        check(
            not page.evaluate("() => document.documentElement.classList.contains('esta-pre-lock')"),
            "第二次不锁滚动",
        )
        check(page.evaluate("() => window.ESTA.preload.skipped === true"), "标记为 skipped")
        ctx.close()

        # ---------------- 3. reduced-motion ----------------
        print("\nprefers-reduced-motion（应整块不出现）")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        page = ctx.new_page()
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(400)
        check(page.query_selector("#esta-preloader") is None, "遮罩已移除")
        check(
            not page.evaluate("() => document.documentElement.classList.contains('esta-pre-lock')"),
            "不锁滚动",
        )
        done_ok = page.evaluate(
            """async () => {
                let settled = false;
                window.ESTA.preload.done.then(() => { settled = true; });
                await new Promise(r => setTimeout(r, 60));
                return settled;
            }"""
        )
        check(done_ok, "done 仍然兑现（否则等它的分镜会挂死）")
        page.screenshot(path=str(SHOTS / "preloader-reduced.png"))
        ctx.close()

        # ---------------- 4. JS 失效时的纯 CSS 兜底 ----------------
        print("\npreloader.js 加载失败（纯 CSS 兜底必须收掉遮罩）")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.route("**/preloader*.js", lambda route: route.abort())
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_timeout(600)
        check(page.query_selector("#esta-preloader") is not None, "遮罩仍在（JS 没跑）")
        drew = page.evaluate(
            """() => {
                const p = document.querySelector('.esta-pre-logo [data-esta-order="1"]');
                if (!p) return null;
                return getComputedStyle(p).strokeDashoffset;
            }"""
        )
        check(drew is not None and drew != "100", "描线仍在播（纯 CSS 驱动）", f"dashoffset={drew}")
        # 兜底在 9s，这里等到 10s
        page.wait_for_timeout(9600)
        hidden = page.evaluate(
            """() => {
                const el = document.getElementById('esta-preloader');
                if (!el) return true;
                const s = getComputedStyle(el);
                return s.visibility === 'hidden' || s.opacity === '0';
            }"""
        )
        check(hidden, "9 秒兜底已收掉遮罩，用户不会被永久挡住")
        ctx.close()

        browser.close()

    print()
    if failures:
        print(f"{len(failures)} 项契约未通过：" + "、".join(failures))
        return 1
    print("加载动画行为契约全部通过")
    print(f"关键帧：{(SHOTS / 'preloader-mid.png').relative_to(REPO)} 等")
    return 0


if __name__ == "__main__":
    sys.exit(main())
