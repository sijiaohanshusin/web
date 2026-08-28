# -*- coding: utf-8 -*-
"""校验素材槽在真实浏览器里的表现。

为什么需要浏览器级的断言：Django 测试能证明 HTML 里有 <img src=...>，但证明
不了那张图**看得见**。真实踩过 —— 图片走廊用 `track.innerHTML += track.innerHTML`
复制内容做无缝循环，innerHTML 重新解析会把 site.js 挂的 load 监听器全部丢掉，
只留下 .img-fade 的 opacity:0，于是整条走廊的懒加载图永久透明。页面不报错、
资源也确实下载成功了，只有截图和计算样式能看出来。

契约：
  1. 走廊渲染出登记表里的每一个槽位（无缝循环会再克隆一份）
  2. 填好图的槽位真的可见：opacity > 0 且 naturalWidth > 0
  3. 克隆出来的那批同样可见（守住上面那个回归）
  4. 空槽位渲染成空焊盘：四角定位标 + 名字 + 拍摄要求
  5. 空槽位与填好图的槽位版面高度一致（aspect-ratio 把位置占住了）
  6. 上传入口只对站务出现
  7. 没有失败请求（不会有引用不存在图片的碎图）

跑法：python scripts/check_slots.py
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


# 把每个槽位的可见性摊平成数据，判断留给 Python
# 只看走廊里的槽位。页面别处也有素材槽（影像区的片头循环，16:9），拿全页去数
# 数量、比高度都会莫名其妙地失败 —— 断言要说清自己在测哪一块。
STATE_JS = """
() => {
  const slots = [...document.querySelectorAll('#nf-strip-track .slot')].map(el => {
    const img = el.querySelector('img');
    const r = el.getBoundingClientRect();
    return {
      key: el.getAttribute('data-slot-key') || '',
      filled: el.classList.contains('is-filled'),
      empty: el.classList.contains('is-empty'),
      h: Math.round(r.height),
      w: Math.round(r.width),
      fids: el.querySelectorAll('.slot-fid').length,
      brief: (el.querySelector('.slot-empty-brief') || {}).textContent || '',
      label: (el.querySelector('.slot-empty-label') || {}).textContent || '',
      cta: !!el.querySelector('.slot-empty-cta, .slot-empty-key'),
      img: img ? {
        opacity: parseFloat(getComputedStyle(img).opacity),
        naturalWidth: img.naturalWidth,
        complete: img.complete,
        cls: img.className,
      } : null,
    };
  });
  return { slots, aspectStyled: [...document.querySelectorAll('.slot')]
      .every(el => (el.getAttribute('style') || '').includes('aspect-ratio')),
    // 全页范围的一条：任何素材槽都不能引用不存在的图
    totalSlots: document.querySelectorAll('.slot').length };
}
"""

# 懒加载图默认要等进视口才下载，而走廊是横向滚动的，右边那几张永远等不到。
# 直接把它们改成 eager 再等 complete —— load 事件照样会触发，所以淡入那条
# 链路依然在被检验。
FORCE_LOAD_JS = """
() => {
  document.querySelectorAll('#nf-strip-track .slot img').forEach(i => { i.loading = 'eager'; });
}
"""

ALL_COMPLETE_JS = """
() => [...document.querySelectorAll('#nf-strip-track .slot img')].every(i => i.complete)
"""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(exist_ok=True)

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        base = f"http://127.0.0.1:{PORT}/"

        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        failed_requests = []
        page.on("requestfailed", lambda r: failed_requests.append(r.url))
        page.on("response", lambda r: failed_requests.append(f"{r.status} {r.url}")
                if r.status >= 400 else None)
        page.goto(base, wait_until="load")
        page.wait_for_function(
            "() => !document.documentElement.classList.contains('esta-pre-lock')",
            timeout=20000)
        page.evaluate(
            "() => document.querySelector('.nf-gallery-section').scrollIntoView()")
        page.wait_for_timeout(400)
        page.evaluate(FORCE_LOAD_JS)
        try:
            page.wait_for_function(ALL_COMPLETE_JS, timeout=15000)
        except Exception:
            pass  # 下面的断言会把没加载完的那张点出来
        # 淡入是 .45s 的 transition，加载完成的那一刻测 opacity 会拿到过渡中的
        # 中间值（实测 0），看起来像图片不可见。等它走完再测。
        page.wait_for_timeout(800)

        st = page.evaluate(STATE_JS)
        slots = st["slots"]

        print("走廊渲染")
        # 无缝循环把内容克隆了一份，所以槽位数是登记顺序的整数倍
        keys_order = [
            "home.gallery.pcb", "home.gallery.group", "home.gallery.etched",
            "home.gallery.lab", "home.gallery.solder", "home.gallery.award",
        ]
        check(len(slots) == len(keys_order) * 2,
              "六个槽位各渲染两份（无缝循环克隆）", f"共 {len(slots)} 个")
        check(st["aspectStyled"], "每个槽位都写了 aspect-ratio 占位")

        heights = {s["h"] for s in slots if s["h"] > 0}
        check(len(heights) == 1,
              "填好图与空槽位版面高度一致（补图前后不用重排）", f"高度集合 {sorted(heights)}")

        print("\n填好图的槽位必须真的看得见")
        filled = [s for s in slots if s["filled"]]
        check(len(filled) >= 2, "至少两个槽位有图", f"{len(filled)} 个")
        for s in filled:
            img = s["img"] or {}
            visible = (img.get("opacity", 0) > 0.01 and img.get("naturalWidth", 0) > 0)
            check(visible, f"有图槽位可见（{img.get('cls') or '无类名'}）",
                  f"opacity={img.get('opacity')} naturalWidth={img.get('naturalWidth')}")

        print("\n空槽位渲染成空焊盘")
        empty = [s for s in slots if s["empty"]]
        check(len(empty) >= 2, "至少两个空槽位", f"{len(empty)} 个")
        for s in empty[:3]:
            check(s["fids"] == 4, f"{s['key']} 有四角定位标", f"{s['fids']} 个")
            check(bool(s["label"].strip()), f"{s['key']} 显示了槽位名称")
            check(len(s["brief"].strip()) > 8, f"{s['key']} 显示了拍摄要求")

        print("\n上传入口只给站务")
        check(not any(s["cta"] for s in slots), "匿名访客看不到上传入口")

        print("\n资源")
        real_failures = [u for u in failed_requests if "favicon" not in u]
        check(not real_failures, "没有失败请求（不会出现碎图）", "; ".join(real_failures[:3]))

        page.screenshot(path=str(SHOTS / "slots-gallery.png"))
        ctx.close()
        browser.close()

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("素材槽契约全部通过")
    print(f"截图在 {SHOTS.relative_to(REPO)}/slots-gallery.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
