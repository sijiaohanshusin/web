# -*- coding: utf-8 -*-
"""校验驾驶舱「素材中心」在真实浏览器里的表现。

Django 测试已经覆盖了权限、清单、表单校验。这里补它证明不了的三件事：

  1. **端到端**：在真实浏览器里选文件、提交，然后去官网确认那一格从占位框变成
     了照片。中间跨了表单编码、文件存储、缓存失效、模板渲染四道环节，任何一道
     断了 Django 测试都可能照样绿（比如缓存没删，测试里 cache 每次都是新的）。
  2. **点预览设焦点**那段脚本 —— 纯前端行为，没有浏览器测不了。而这是站务唯一
     会用的设焦点方式（没人愿意去想「主体在横向 38% 处」）。
  3. **深链**从官网占位框点过来，是否真的高亮并展开了对应那张卡片。

跑完会把自己上传的东西删掉，可以反复跑。

跑法：python scripts/check_media_center.py
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

from shoot import PORT, DevServer, do_login  # noqa: E402

SHOTS = REPO / ".shots"
# 拿走廊里的一格做端到端实验：它在首页上，公开侧一眼就能看到。
# **它现在在登记表里有静态兜底**（img/photo/lab-debug.webp，2024 TI 杯赛场调试），
# 所以这个脚本验的是「站务上传的那份盖过静态兜底、删掉之后回落到兜底」，
# 不是「占位框变成照片」。空焊盘那一态由 check_slots 在 /recruit/ 上验
# （recruit.training.session 是登记表里唯一一个真的没有兜底的图片槽）。
KEY = "home.gallery.lab"
failures = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


def slot_state(ppage, key):
    """公开页面上那一格的实况：填没填、图到底是哪一份。

    **判据要看「引的是哪个文件」，不能看「有没有 data-slot-key」。** 那个钩子
    三种状态都发（语义是「这一格是哪个槽位」），拿它当「填没填」的判据，一个方向
    必然失败、另一个方向必然通过 —— 这个脚本原来两条都踩了。
    """
    return ppage.evaluate(
        """(key) => {
            const el = document.querySelector('[data-slot-key="' + key + '"]');
            if (!el) return null;
            const img = el.querySelector('img');
            return {
              empty: el.classList.contains('is-empty'),
              filled: el.classList.contains('is-filled'),
              src: img ? img.getAttribute('src') : '',
              alt: img ? img.getAttribute('alt') : '',
            };
        }""", key)


def make_sample() -> Path:
    """画一张能一眼认出来的测试图（青底 + 一条铜色斜带）。"""
    from PIL import Image, ImageDraw

    path = SHOTS / "sample-upload.png"
    img = Image.new("RGB", (800, 600), (13, 169, 205))
    d = ImageDraw.Draw(img)
    d.polygon([(0, 600), (800, 0), (800, 160), (160, 600)], fill=(201, 138, 61))
    img.save(path)
    return path


def cleanup():
    """把测试数据清掉，让脚本可以反复跑。"""
    import django

    django.setup()
    from core.models import MediaSlot

    for obj in MediaSlot.objects.filter(key=KEY):
        obj.image.delete(save=False)
        obj.delete()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    import dev_account

    SHOTS.mkdir(exist_ok=True)
    user, password = dev_account.ensure()
    cleanup()          # 上一轮可能留了东西
    sample = make_sample()

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        base = f"http://127.0.0.1:{PORT}"
        media_url = f"{base}/dashboard/media/"

        # ---------------- 未登录 ----------------
        print("权限")
        anon = browser.new_context(viewport={"width": 1440, "height": 900})
        page = anon.new_page()
        page.goto(media_url, wait_until="domcontentloaded")
        check("/accounts/login" in page.url, "未登录访问被送去登录页", page.url)
        anon.close()

        # ---------------- 站务 ----------------
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        errors = []
        bad_requests = []
        ctx.on("weberror", lambda e: errors.append(str(e)))
        do_login(ctx, base, f"{user}:{password}")

        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("response", lambda r: bad_requests.append(f"{r.status} {r.url}")
                if r.status >= 400 else None)

        print("\n清单")
        page.goto(media_url, wait_until="load")
        cards = page.eval_on_selector_all(
            "[data-slot-card]", "els => els.map(e => e.getAttribute('data-slot-card'))")
        from core import slots as registry  # django 已在 cleanup 里 setup 过

        check(set(cards) == set(registry.REGISTRY),
              "登记表里每个槽位都列出来了（包括数据库里没有记录的）",
              f"{len(cards)} 张卡片")
        badge = page.eval_on_selector(
            ".dash-nav .dash-badge", "el => el.textContent.trim()") \
            if page.query_selector(".dash-nav .dash-badge") else "0"
        expected_missing = sum(1 for s in registry.SLOTS if not s.fallback)
        check(str(expected_missing) in page.content(), "侧边栏徽标显示缺图数",
              f"徽标 {badge} / 期望 {expected_missing}")

        todo_states = page.eval_on_selector_all(
            ".ms-todo-item", "els => els.map(e => e.className)")
        first_non_missing = next(
            (i for i, c in enumerate(todo_states) if "is-missing" not in c), len(todo_states))
        check(all("is-missing" in c for c in todo_states[:first_non_missing])
              and all("is-missing" not in c for c in todo_states[first_non_missing:]),
              "缺图清单把「空着」排在「有兜底图」前面")

        # ---------------- 深链 ----------------
        print("\n从官网占位框点过来")
        page.goto(f"{media_url}?key={KEY}", wait_until="load")
        page.wait_for_timeout(300)
        state = page.evaluate(
            """(key) => {
                let hit = null;
                document.querySelectorAll('[data-slot-card]').forEach(c => {
                    if (c.getAttribute('data-slot-card') === key) hit = c;
                });
                if (!hit) return null;
                const box = hit.querySelector('[data-ms-form]');
                return { focused: hit.classList.contains('is-focused'),
                         open: !!(box && box.open) };
            }""", KEY)
        check(state and state["focused"], "对应卡片被高亮")
        check(state and state["open"], "对应卡片的上传表单自动展开")

        # ---------------- 端到端上传 ----------------
        print("\n上传 → 官网生效")
        prefix = KEY.replace(".", "_")
        page.set_input_files(f'input[name="{prefix}-image"]', str(sample))
        page.fill(f'input[name="{prefix}-alt"]', "自动化上传的实验室照片")
        page.fill(f'input[name="{prefix}-caption"]', "焊台与示波器")
        with page.expect_navigation():
            page.click(f'[data-slot-card="{KEY}"] .ms-form-ops button[type=submit]')
        check("已保存" in page.content(), "保存成功并给出反馈")

        after = page.evaluate(
            """(key) => {
                let hit = null;
                document.querySelectorAll('[data-slot-card]').forEach(c => {
                    if (c.getAttribute('data-slot-card') === key) hit = c;
                });
                if (!hit) return null;
                const img = hit.querySelector('.ms-preview img');
                return { hasImg: !!img, src: img ? img.getAttribute('src') : "" };
            }""", KEY)
        check(after and after["hasImg"], "卡片预览换成了刚上传的图",
              (after or {}).get("src", ""))
        check("/media/slots/" in (after or {}).get("src", ""),
              "图存到了 media/slots/ 下（公开可访问的目录）")

        # 官网那一格必须同步变成刚上传的那张 —— 这一步同时验证了缓存失效
        public = browser.new_context(viewport={"width": 1440, "height": 900})
        ppage = public.new_page()
        ppage.goto(f"{base}/", wait_until="domcontentloaded")
        st = slot_state(ppage, KEY)
        check(st is not None, "官网上找得到这一格", KEY)
        check(bool(st) and st["alt"] == "自动化上传的实验室照片",
              "官网那一格已经变成刚上传的那张（缓存已失效）", (st or {}).get("alt", ""))
        # 这里原来写的是「HTML 里不再出现 data-slot-key」。那条判据只在
        # `data-slot-key` 还**只由空态模板发出**的年代成立 —— 这个钩子后来改成
        # 三种状态都发（语义是「这一格是哪个槽位」，和填没填图无关），于是它从此
        # 必然失败。而没人发现，因为这个脚本在那次改动之后一直没被跑过。
        # 现在验真正该验的那件事：**上传的那份盖过了登记表里的静态兜底**。
        check(bool(st) and st["src"].startswith("/media/slots/") and not st["empty"],
              "**上传的那份盖过了静态兜底**（取用优先级：数据库 → 登记表 → 空焊盘）",
              (st or {}).get("src", ""))
        public.close()

        # ---------------- 点预览设焦点 ----------------
        print("\n点预览设焦点")
        page.goto(f"{media_url}?key={KEY}", wait_until="load")
        page.wait_for_timeout(400)
        box = page.eval_on_selector(
            f'[data-slot-card="{KEY}"] .ms-preview img',
            "el => { const r = el.getBoundingClientRect();"
            "        return {x: r.x, y: r.y, w: r.width, h: r.height}; }")
        before = page.input_value(f'input[name="{prefix}-focal_x"]')
        # 点画面左上四分之一处，期望 focal 大致落在 25% / 25%
        page.mouse.click(box["x"] + box["w"] * 0.25, box["y"] + box["h"] * 0.25)
        fx = int(page.input_value(f'input[name="{prefix}-focal_x"]'))
        fy = int(page.input_value(f'input[name="{prefix}-focal_y"]'))
        check(before == "50", "初始焦点是居中", before)
        check(20 <= fx <= 30 and 20 <= fy <= 30,
              "点击位置写进了焦点输入框", f"{fx}% {fy}%")
        pos = page.eval_on_selector(
            f'[data-slot-card="{KEY}"] .ms-preview img',
            "el => el.style.objectPosition")
        check("25%" in pos or "26%" in pos or "24%" in pos,
              "预览立刻按新焦点重排（即时反馈）", pos)

        # 不截 full_page：这一页有两三千像素高，超过读图工具的 2000px 上限，
        # 截出来也读不了。要看全貌用 crop.py --rows 切片。
        page.screenshot(path=str(SHOTS / "media-center.png"))

        # ---------------- 删除，回落到静态兜底 ----------------
        print("\n删除 → 回落到登记表里的静态兜底")
        page.once("dialog", lambda d: d.accept())
        with page.expect_navigation():
            page.click(f'[data-slot-card="{KEY}"] button[value="delete"]')
        check("已删除" in page.content(), "删除成功并给出反馈")

        public = browser.new_context(viewport={"width": 1440, "height": 900})
        ppage = public.new_page()
        ppage.goto(f"{base}/", wait_until="domcontentloaded")
        st = slot_state(ppage, KEY)
        # 这里原来写的是「HTML 里还有 data-slot-key」。那个钩子三种状态都发，
        # 所以那条断言在「什么都没发生」时同样成立 —— 等于没写，而且一路绿灯。
        check(bool(st) and "/media/slots/" not in st["src"],
              "删掉之后官网不再引用上传的那份", (st or {}).get("src", ""))
        check(bool(st) and "lab-debug" in st["src"] and not st["empty"],
              "**回落到登记表里的静态兜底**（这一格有兜底，不该变成空焊盘）",
              (st or {}).get("src", ""))
        public.close()

        print("\n运行时")
        check(not errors, "无未捕获异常", "; ".join(errors[:2]))
        real_bad = [u for u in bad_requests if "favicon" not in u]
        check(not real_bad, "无失败请求", "; ".join(real_bad[:3]))

        ctx.close()
        browser.close()

    cleanup()
    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("素材中心契约全部通过")
    print(f"截图在 {SHOTS.relative_to(REPO)}/media-center.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
