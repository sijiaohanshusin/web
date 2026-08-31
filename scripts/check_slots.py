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

第 4、5 条量在**新生指南**上，不在首页走廊上。首页那六格已经全部补上照片了，
拿它去验空态就是在拿一个没有空槽位的地方数空槽位 —— 断言不会红，只会空跑
（`至少两个空槽位` 直接判 0 >= 2 失败，更差的写法则是悄悄通过）。指南那三格
现场照同比例（16/9）、一填两空，正好是「补图前后不用重排」的现成样本。

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


def check_ratios(items):
    """每一格的实测宽高比必须等于它声明的 aspect-ratio。

    这是「aspect-ratio 把版面占住了」唯一站得住的判据。原来写的是「所有槽位
    高度相等」—— 那条只在「所有格子同比例、同容器宽度」时才成立，而这两个
    前提都不是契约：走廊已经是等高胶片条（合影那格 12:5 就该比别人宽），指南
    那三格里有一格在折叠块里、容器窄 46px。
    """
    for s in items:
        if not s["ratio"] or s["h"] <= 0:
            check(False, f"{s['key'] or '无 key'} 没有写 aspect-ratio", "style 里没抠到比例")
            continue
        a, b = s["ratio"]
        want = s["w"] * b / a
        state = "填好图" if s["filled"] else "空焊盘"
        check(abs(s["h"] - want) <= 2,
              f"{s['key']}（{state}）按 {a:g}/{b:g} 占位",
              f"宽 {s['w']} → 实测高 {s['h']}，应为 {want:.0f}")


# 把每个槽位的可见性摊平成数据，判断留给 Python。
# 选择器由调用方传入，不写死 —— 页面别处也有素材槽（首页影像区的片头循环是
# 16:9），拿全页去数数量、比高度都会莫名其妙地失败。断言要说清自己在测哪一块。
STATE_JS = """
(sel) => {
  const slots = [...document.querySelectorAll(sel)].map(el => {
    const img = el.querySelector('img');
    const r = el.getBoundingClientRect();
    return {
      key: el.getAttribute('data-slot-key') || '',
      filled: el.classList.contains('is-filled'),
      empty: el.classList.contains('is-empty'),
      h: Math.round(r.height),
      w: Math.round(r.width),
      // 声明的比例，从内联 style 里抠出来。拿它和实测宽高比一比，才算证明了
      // 「aspect-ratio 真的把版面占住了」—— 只看两个槽位高度相不相等是不够的，
      // 它们的容器宽度可能压根不一样（折叠块里那格就窄 46px）。
      ratio: ((el.getAttribute('style') || '')
        .match(/aspect-ratio:\\s*([\\d.]+)\\s*\\/\\s*([\\d.]+)/) || []).slice(1).map(Number),
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

# 「胶片条的宽度是从比例算出来的」——**直接量机制，不靠现有照片的比例去证。**
# 原来这件事是用「六格宽度不全相同」证的，而那时走廊里有一格 12:5 的宽幅合影。
# 那张合影搬去了分镜 02 的整宽带之后六格同为 4:3，宽度本来就该全相同，那条断言
# 从「守着一件事」直接变成「必然失败」。
# 现在的判据：临时把第一格的 aspect-ratio 改成 2/1，宽度应当按比例跟着变。
# 写死宽度的话它一动不动 —— 那正是要拦的退步（下一张非 4:3 的照片会被压扁，
# 上下多出天花板和地砖，而页面照常渲染、控制台干净）。
# 量完把 style 属性**原样**摆回去：后面的断言和截图不能看到被改过的版面。
WIDTH_DERIVED_JS = """
(sel) => {
  const el = document.querySelector(sel);
  if (!el) return { ok: false };
  const style = el.getAttribute('style');
  const m = (style || '').match(/aspect-ratio:\\s*([\\d.]+)\\s*\\/\\s*([\\d.]+)/);
  if (!m) return { ok: false };
  const before = el.getBoundingClientRect().width;
  el.style.aspectRatio = '2 / 1';
  const after = el.getBoundingClientRect().width;
  if (style === null) el.removeAttribute('style'); else el.setAttribute('style', style);
  return {
    ok: true,
    ratio: m[1] + '/' + m[2],
    before: Math.round(before),
    after: Math.round(after),
    want: before * 2 / (Number(m[1]) / Number(m[2])),
    restored: Math.round(el.getBoundingClientRect().width),
  };
}
"""

# 分镜 02 末尾的整宽合影带。这一格和走廊里的格子性质不同，所以单独量：
# 它是 section 的直接子元素（靠 `.nf-section` 左右内边距为 0 实现全出血），
# 而且**刻意不压暗、图注不叠在照片上** —— 那两件事一旦被「顺手统一成和走廊
# 一样」，页面照常渲染，只是六十张脸糊掉了。
BAND_JS = """
() => {
  const el = document.querySelector('[data-slot-key="home.legacy.group"]');
  if (!el) return { found: false };
  const r = el.getBoundingClientRect();
  const img = el.querySelector('img');
  const cap = document.querySelector('.nf-legacy-cap');
  const m = ((el.getAttribute('style') || '')
      .match(/aspect-ratio:\\s*([\\d.]+)\\s*\\/\\s*([\\d.]+)/) || []).slice(1).map(Number);
  return {
    found: true,
    filled: el.classList.contains('is-filled'),
    w: Math.round(r.width), h: Math.round(r.height),
    left: Math.round(r.left), bottom: Math.round(r.bottom),
    viewport: document.documentElement.clientWidth,
    ratio: m,
    radius: getComputedStyle(el).borderTopLeftRadius,
    opacity: img ? parseFloat(getComputedStyle(img).opacity) : 0,
    filter: img ? getComputedStyle(img).filter : '',
    naturalWidth: img ? img.naturalWidth : 0,
    hasCap: !!cap,
    // 图注在照片**里面**就意味着它叠在照片上，那就得把照片压暗才够对比度
    capInsidePhoto: cap ? el.contains(cap) : null,
    capTop: cap ? Math.round(cap.getBoundingClientRect().top) : 0,
    capColor: cap ? getComputedStyle(cap).color : '',
  };
}
"""

# 懒加载图默认要等进视口才下载，而走廊是横向滚动的，右边那几张永远等不到。
# 直接把它们改成 eager 再等 complete —— load 事件照样会触发，所以淡入那条
# 链路依然在被检验。
FORCE_LOAD_JS = """
(sel) => {
  document.querySelectorAll(sel + ' img').forEach(i => { i.loading = 'eager'; });
}
"""

ALL_COMPLETE_JS = """
(sel) => [...document.querySelectorAll(sel + ' img')].every(i => i.complete)
"""

# 指南那三格现场照有两格在折叠块里（`<details class="fold">`，默认收着）。
# 收着的时候高度是 0，直接量会得到「空槽位高 0、填好图高 337」，看着像 bug。
# 展开后要等 .45s 的高度过渡走完再量。
OPEN_FOLDS_JS = """
() => { document.querySelectorAll('details.fold').forEach(d => { d.open = true; }); }
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
        STRIP = "#nf-strip-track .slot"
        page.evaluate(FORCE_LOAD_JS, STRIP)
        try:
            page.wait_for_function(ALL_COMPLETE_JS, arg=STRIP, timeout=15000)
        except Exception:
            pass  # 下面的断言会把没加载完的那张点出来
        # 淡入是 .45s 的 transition，加载完成的那一刻测 opacity 会拿到过渡中的
        # 中间值（实测 0），看起来像图片不可见。等它走完再测。
        page.wait_for_timeout(800)

        st = page.evaluate(STATE_JS, STRIP)
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
        # 每一格都要带 key。这个钩子填没填图都要发 —— 它原来只在空态里，
        # 于是给某个槽位补一张兜底图，「走廊里有哪几个槽位」就无从查证了。
        check(sorted(s["key"] for s in slots) == sorted(keys_order * 2),
              "每一格都带着自己的 data-slot-key",
              f"实际 {sorted({s['key'] for s in slots})}")

        # 等高胶片条：高度必须一致，宽度由各自的比例算出来（判据见 WIDTH_DERIVED_JS
        # 上面那段 —— 不拿「现在的六张照片比例正好不同」当证据）。
        heights = {s["h"] for s in slots if s["h"] > 0}
        check(len(heights) == 1, "走廊各格等高（胶片条）", f"高度集合 {sorted(heights)}")
        probe = page.evaluate(WIDTH_DERIVED_JS, STRIP)
        check(probe.get("ok"), "抠到了第一格的 aspect-ratio（不然下面两条空跑）",
              probe.get("ratio", "没抠到"))
        if probe.get("ok"):
            check(abs(probe["after"] - probe["want"]) <= 2,
                  "**宽度是从 aspect-ratio 算出来的**（不是写死的）",
                  f"把 {probe['ratio']} 临时改成 2/1：宽 {probe['before']} → "
                  f"{probe['after']}，应为 {probe['want']:.0f}")
            check(probe["restored"] == probe["before"],
                  "量完把比例摆回去了（后面的断言看的是原版面）",
                  f"{probe['restored']} == {probe['before']}")
        print()
        check_ratios(slots[: len(keys_order)])

        print("\n填好图的槽位必须真的看得见")
        filled = [s for s in slots if s["filled"]]
        check(len(filled) == len(keys_order) * 2,
              "走廊六格全部有图（克隆的那批也算）", f"{len(filled)} / {len(slots)}")
        for s in filled:
            img = s["img"] or {}
            visible = (img.get("opacity", 0) > 0.01 and img.get("naturalWidth", 0) > 0)
            check(visible, f"有图槽位可见（{s['key'] or '无 key'}）",
                  f"opacity={img.get('opacity')} naturalWidth={img.get('naturalWidth')}")

        print("\n上传入口只给站务（首页）")
        check(not any(s["cta"] for s in slots), "匿名访客看不到上传入口")

        page.screenshot(path=str(SHOTS / "slots-gallery.png"))

        # ------------------------------------------------------------------
        # 分镜 02 末尾的整宽合影带
        # ------------------------------------------------------------------
        print("\n分镜 02 末尾的整宽合影带（home.legacy.group）")
        BAND = '[data-slot-key="home.legacy.group"]'
        page.evaluate(FORCE_LOAD_JS, BAND)
        try:
            page.wait_for_function(ALL_COMPLETE_JS, arg=BAND, timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(800)
        b = page.evaluate(BAND_JS)
        check(b["found"], "整宽带渲染了")
        if b["found"]:
            check(b["filled"], "带子里有图（兜底图或站务上传的）",
                  f"naturalWidth={b['naturalWidth']}")
            # 全出血：这一块刻意放在 .container 外面。哪天被谁包进容器里，
            # 版面照常渲染 —— 只是两侧多出 100px 留白、"整宽"这件事没了。
            check(b["left"] == 0 and abs(b["w"] - b["viewport"]) <= 1,
                  "**左右都到屏幕边缘**（放在 .container 外面才有的效果）",
                  f"left={b['left']} 宽 {b['w']} / 视口 {b['viewport']}")
            check(b["ratio"] == [16, 5], "比例是 16/5", f"实际 {b['ratio']}")
            if b["ratio"]:
                want_h = b["w"] * b["ratio"][1] / b["ratio"][0]
                check(abs(b["h"] - want_h) <= 2, "高度按比例占住了",
                      f"宽 {b['w']} → 实测高 {b['h']}，应为 {want_h:.0f}")
            check(b["radius"] == "0px",
                  "没有圆角（全出血的东西带圆角会在屏幕边缘露出黑角）",
                  f"border-radius {b['radius']}")
            # 下面两条守的是同一个决定：这一格的全部内容就是六十张脸，
            # 任何压暗都在毁它。所以图注放在照片**外面**的纯黑底上。
            check(b["opacity"] == 1 and b["filter"] in ("none", ""),
                  "**照片保持原亮度**（没被压暗去给图注让对比度）",
                  f"opacity={b['opacity']} filter={b['filter'] or 'none'}")
            check(b["hasCap"] and b["capInsidePhoto"] is False
                  and b["capTop"] >= b["bottom"] - 1,
                  "**图注在照片下面，不叠在照片上**",
                  f"图注顶 {b['capTop']} / 照片底 {b['bottom']}，"
                  f"在照片内={b['capInsidePhoto']}")
        page.evaluate("(sel) => document.querySelector(sel)"
                      ".scrollIntoView({block: 'center', behavior: 'instant'})", BAND)
        page.wait_for_timeout(400)
        page.screenshot(path=str(SHOTS / "slots-legacy-band.png"))

        # ------------------------------------------------------------------
        # 空焊盘量在新生指南上：首页六格已经全部补齐照片，那里再没有空态可量。
        # 指南三格现场照同为 16/9，一填两空 —— 「补图前后不用重排」这条性质
        # 需要两态同时在场才证明得了。
        # ------------------------------------------------------------------
        SHOT = ".rg-shot"
        page.goto(base + "recruit/", wait_until="load")
        page.wait_for_function(
            "() => !document.documentElement.classList.contains('esta-pre-lock')",
            timeout=20000)
        page.evaluate(OPEN_FOLDS_JS)
        page.wait_for_timeout(700)          # 折叠块的高度过渡是 .45s
        page.evaluate(FORCE_LOAD_JS, SHOT)
        try:
            page.wait_for_function(ALL_COMPLETE_JS, arg=SHOT, timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(800)

        shots = page.evaluate(STATE_JS, SHOT)["slots"]

        print("\n新生指南 · 每章一张现场照")
        check(len(shots) == 3, "三章各一格现场照", f"{len(shots)} 格")
        empty = [s for s in shots if s["empty"]]
        filled_shots = [s for s in shots if s["filled"]]
        check(bool(empty) and bool(filled_shots),
              "填好图与空焊盘同时在场（旧轮播做不到的那件事）",
              f"{len(filled_shots)} 填 / {len(empty)} 空")

        # 「补图前后不用重排」= 两态都按自己声明的比例占位。
        check_ratios(shots)

        print("\n空槽位渲染成空焊盘")
        for s in empty:
            check(s["fids"] == 4, f"{s['key']} 有四角定位标", f"{s['fids']} 个")
            check(bool(s["label"].strip()), f"{s['key']} 显示了槽位名称")
            check(len(s["brief"].strip()) > 8, f"{s['key']} 显示了拍摄要求")

        print("\n上传入口只给站务（新生指南）")
        check(not any(s["cta"] for s in shots), "匿名访客看不到上传入口")

        print("\n资源")
        real_failures = [u for u in failed_requests if "favicon" not in u]
        check(not real_failures, "没有失败请求（不会出现碎图）", "; ".join(real_failures[:3]))

        # 截图要落在被检查的格子上，不是页面顶部。两态各拍一张：占位框的内容由
        # 上面的断言逐项验过，照片本身只能靠眼睛看（构图对不对、有没有糊）。
        for sel, name in ((".rg-shot.is-empty", "slots-guide-empty"),
                          (".rg-shot.is-filled", "slots-guide-filled")):
            page.evaluate(
                f"() => document.querySelector('{sel}')"
                ".scrollIntoView({ block: 'center' })")
            # `scroll-behavior: smooth` 跨几千像素要一秒多，固定等待会在半路采样，
            # 拍到「跳歪了」的位置。轮询到 scrollY 不再变化再拍。
            prev, same = -1, 0
            while same < 3:
                y = page.evaluate("() => Math.round(window.scrollY)")
                same = same + 1 if y == prev else 0
                prev = y
                page.wait_for_timeout(120)
            page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)
        ctx.close()
        browser.close()

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("素材槽契约全部通过")
    print(f"截图在 {SHOTS.relative_to(REPO)}/ ：slots-gallery.png、"
          "slots-legacy-band.png、slots-guide-empty.png、slots-guide-filled.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
