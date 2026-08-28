# -*- coding: utf-8 -*-
"""校验作品墙：公开边界、缺图占位、筛选、详情页、首页精选入口。

这一页的风险集中在**可见性**和**媒体路径**两件事上：

  1. `Project` 一个模型两副面孔（会员档案 / 对外展示）。只要有一处用了
     `Project.objects` 而不是 `Project.public()`，外人拿到一个 id 就能读到还没
     准备好公开的项目简介 —— 页面正常渲染，没有任何报错。
  2. **展示图必须落在 `/media/works/` 下**。nginx 对 `/media/projects/` 返回 403
     （那里是会员私有文件，要经 X-Accel-Redirect 鉴权才发）。放错路径的后果是
     线上一片碎图，而本地开发用 Django 直接服务 media，一切正常 —— 这类 bug
     只有断言路径才能在部署前拦住。

跑法：python scripts/check_works.py
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "app"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

from shoot import PORT, DevServer, do_login  # noqa: E402

SHOTS = REPO / ".shots"
SEED_PREFIX = "自动化作品"
failures = []


def check(cond, label, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        failures.append(label)


WALL = """
() => {
    const cards = [...document.querySelectorAll('.wk-card')];
    return {
        count: cards.length,
        titles: cards.map(c => (c.querySelector('.wk-card-title') || {}).textContent.trim()),
        hrefs: cards.map(c => c.getAttribute('href')),
        covers: cards.map(c => {
            const img = c.querySelector('.wk-cover img');
            return img ? img.getAttribute('src') : null;
        }),
        emptyCovers: cards.filter(c => c.querySelector('.wk-cover.is-empty')).length,
        fidsOnEmpty: cards.reduce((n, c) => {
            const e = c.querySelector('.wk-cover.is-empty');
            return n + (e ? e.querySelectorAll('.slot-fid').length : 0);
        }, 0),
        tabs: [...document.querySelectorAll('.wk-filter .pill')]
            .map(a => a.textContent.replace(/\\s+/g, ' ').trim()),
        empty: !!document.querySelector('.empty-state'),
        emptyText: (document.querySelector('.empty-state') || {}).textContent || '',
    };
}
"""

DETAIL = """
() => ({
    title: (document.querySelector('.wk-detail-hero h1') || {}).textContent.trim(),
    shots: document.querySelectorAll('.wk-gallery .wk-shot').length,
    shotSrcs: [...document.querySelectorAll('.wk-shot img')].map(i => i.getAttribute('src')),
    team: [...document.querySelectorAll('.wk-team strong')].map(e => e.textContent.trim()),
    hasArchiveLink: !!document.querySelector('a[href*="/projects/"]'),
    // 收窄到 hero：页面底部「还有这些」的卡片上也有 .wk-tags，
    // 数全页会把别的作品的标签算进来（第一次就这么错了，读到 5 个）
    tags: [...document.querySelectorAll('.wk-detail-hero .wk-tags li')]
        .map(e => e.textContent.trim()),
    more: document.querySelectorAll('.wk-card').length,
})
"""

HOME_WORKS = """
() => {
    const sec = document.getElementById('nf-works');
    if (!sec) return { present: false };
    return {
        present: true,
        cards: sec.querySelectorAll('.wk-card').length,
        titles: [...sec.querySelectorAll('.wk-card-title')].map(e => e.textContent.trim()),
        moreHref: (sec.querySelector('.nf-link-more') || {}).getAttribute
            ? sec.querySelector('.nf-link-more').getAttribute('href') : null,
    };
}
"""


def png(color=(13, 169, 205), size=(640, 480)):
    from io import BytesIO

    from django.core.files.base import ContentFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return ContentFile(buf.getvalue(), name="cover.png")


def wipe():
    from projects.models import Project

    for p in Project.objects.filter(name__startswith=SEED_PREFIX):
        if p.cover:
            p.cover.delete(save=False)
        for s in p.shots.all():
            s.image.delete(save=False)
        p.delete()


def seed():
    """建四件作品，覆盖「有封面/没封面」「精选/不精选」「公开/不公开」。"""
    from django.contrib.auth import get_user_model

    from projects.models import Project, ProjectMember, ProjectShot

    wipe()
    User = get_user_model()
    author = User.objects.filter(username="shootbot").first()

    made = {}
    made["featured"] = Project.objects.create(
        name=f"{SEED_PREFIX}·自制万用表", department=Project.Department.HARDWARE,
        summary="大一下的合作任务：从量程切换电路到外壳，全部自己做。",
        highlight="量程自动切换，误差 1% 以内", tags="运放, PCB, 电赛",
        is_public=True, is_featured=True, cover=png((201, 138, 61)),
    )
    made["featured2"] = Project.objects.create(
        name=f"{SEED_PREFIX}·循迹小车", department=Project.Department.JOINT,
        summary="STM32 + 灰度传感器阵列，PID 调参调了两周。",
        highlight="全程无干预跑完赛道", tags="STM32, PID",
        is_public=True, is_featured=True, cover=png((13, 169, 205)),
    )
    # 没有封面：卡片应当显示空焊盘占位，而不是碎图或被藏起来
    made["nocover"] = Project.objects.create(
        name=f"{SEED_PREFIX}·音乐盒", department=Project.Department.SOFTWARE,
        summary="第一次任务，用蜂鸣器把一首歌敲出来。",
        is_public=True,
    )
    # 不公开：作品墙上不能出现，直接访问它的展示页要 404
    made["private"] = Project.objects.create(
        name=f"{SEED_PREFIX}·未公开的东西", department=Project.Department.HARDWARE,
        summary="还没整理好，不该被外人看到。",
        is_public=False,
    )

    ProjectShot.objects.create(project=made["featured"], image=png((90, 90, 90)),
                               caption="焊完的主板", sort_order=10)
    ProjectShot.objects.create(project=made["featured"], image=png((60, 60, 60)),
                               caption="装进外壳", sort_order=20)
    if author:
        ProjectMember.objects.get_or_create(
            project=made["featured"], user=author,
            defaults={"role": ProjectMember.Role.LEAD},
        )
    return {k: v.pk for k, v in made.items()}


def unfeature_all():
    from projects.models import Project

    Project.objects.filter(name__startswith=SEED_PREFIX).update(is_featured=False)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from playwright.sync_api import sync_playwright

    import django

    SHOTS.mkdir(exist_ok=True)
    django.setup()

    import dev_account

    user, password = dev_account.ensure(level=4)   # 站务：验「打开档案」入口
    ids = seed()
    print(f"已建 {len(ids)} 件作品（含 1 件不公开、1 件没封面）")

    with DevServer(PORT), sync_playwright() as p:
        browser = p.chromium.launch()
        base = f"http://127.0.0.1:{PORT}"
        vp = {"width": 1440, "height": 1000}

        errors, failed = [], []

        def watch(page):
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("requestfailed", lambda r: failed.append(r.url))
            page.on("response",
                    lambda r: failed.append(f"{r.url} HTTP {r.status}") if r.status >= 400 else None)

        # ---------------- 作品墙 ----------------
        print("\n作品墙：只出公开的")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        watch(page)
        page.goto(base + "/works/", wait_until="load")
        page.wait_for_timeout(500)
        st = page.evaluate(WALL)
        check(st["count"] == 3, "三件公开作品都在", f"{st['count']} 件")
        check(not any("未公开" in t for t in st["titles"]),
              "不公开的作品没有出现在墙上", str(st["titles"]))
        check(st["emptyCovers"] == 1, "没封面的那件渲染成空焊盘占位（不是碎图）",
              f"{st['emptyCovers']} 个占位")
        check(st["fidsOnEmpty"] == 4, "占位框有四角定位标", f"{st['fidsOnEmpty']} 个")

        # 这一条是本任务的硬约束：nginx 对 /media/projects/ 返回 403
        real = [c for c in st["covers"] if c]
        check(all("/media/works/" in c for c in real),
              "封面都落在 /media/works/ 下（/media/projects/ 会被 nginx 403）",
              str(real))
        check(not any("/media/projects/" in (c or "") for c in st["covers"]),
              "没有任何展示图指向 /media/projects/")

        # 筛选条：只列真的有作品的方向
        check(len(st["tabs"]) == 4, "筛选条 = 全部 + 三个有作品的方向",
              str(st["tabs"]))
        check(not any("其他" in t for t in st["tabs"]),
              "没有作品的方向不出现在筛选条上（点进去一片空白更糟）")
        page.screenshot(path=str(SHOTS / "works-wall.png"))

        page.click('.wk-filter .pill[href="?dept=hardware"]')
        page.wait_for_load_state("load")
        page.wait_for_timeout(400)
        st = page.evaluate(WALL)
        check(st["count"] == 1 and "万用表" in st["titles"][0],
              "按方向筛选只剩那一件", str(st["titles"]))
        ctx.close()

        # ---------------- 不公开的作品不能被 id 猜到 ----------------
        print("\n公开边界")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        resp = page.goto(f"{base}/works/{ids['private']}/", wait_until="load")
        check(resp.status == 404, "直接访问不公开作品的展示页是 404",
              f"HTTP {resp.status}")
        body = page.evaluate("() => document.body.textContent")
        check("还没整理好" not in body, "404 页面没有泄漏项目简介")
        ctx.close()

        # ---------------- 详情页（外人视角） ----------------
        print("\n作品详情（未登录）")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        watch(page)
        page.goto(f"{base}/works/{ids['featured']}/", wait_until="load")
        page.wait_for_timeout(500)
        d = page.evaluate(DETAIL)
        check("万用表" in d["title"], "标题是这件作品", d["title"])
        check(d["shots"] == 2, "图集两张都在", f"{d['shots']} 张")
        check(all("/media/works/" in s for s in d["shotSrcs"]),
              "图集也走 /media/works/", str(d["shotSrcs"][:2]))
        check(len(d["tags"]) == 3, "标签渲染成三个", str(d["tags"]))
        check(bool(d["team"]), "「做的人」列出来了", str(d["team"]))
        check(not d["hasArchiveLink"], "外人看不到「打开档案」入口")
        check(d["more"] == 2, "底部推荐另外两件", f"{d['more']} 件")
        page.screenshot(path=str(SHOTS / "works-detail.png"))
        ctx.close()

        # ---------------- 详情页（站务视角） ----------------
        print("\n作品详情（站务登录）")
        ctx = browser.new_context(viewport=vp)
        do_login(ctx, base, f"{user}:{password}")
        page = ctx.new_page()
        page.goto(f"{base}/works/{ids['featured']}/", wait_until="load")
        page.wait_for_timeout(400)
        d = page.evaluate(DETAIL)
        check(d["hasArchiveLink"], "站务能看到「打开档案」入口")
        ctx.close()

        # ---------------- 首页分镜 07 ----------------
        print("\n首页分镜 07：只出精选")
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        watch(page)
        page.goto(base + "/", wait_until="load")
        page.wait_for_timeout(1200)
        h = page.evaluate(HOME_WORKS)
        check(h["present"], "有精选作品时分镜 07 出现")
        check(h["cards"] == 2, "只展示精选的那两件", f"{h['cards']} 件")
        check(not any("音乐盒" in t for t in h["titles"]),
              "非精选的公开作品不上首页", str(h["titles"]))
        check(h["moreHref"] == "/works/", "「看全部作品」指向作品墙", str(h["moreHref"]))
        check(not errors, "无未捕获异常", "; ".join(errors[:2]))
        check(not failed, "无失败请求（封面与图集都可达）", "; ".join(failed[:3]))
        ctx.close()

        # ---------------- 没有精选时整段不渲染 ----------------
        print("\n一件精选都没有时分镜 07 必须整段消失")
        unfeature_all()
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        page.goto(base + "/", wait_until="load")
        page.wait_for_timeout(900)
        h = page.evaluate(HOME_WORKS)
        check(not h["present"],
              "分镜 07 不渲染（空壳区块比没有这段更糟）")
        body = page.evaluate("() => document.body.textContent")
        check("敬请期待" not in body, "也没有留下「敬请期待」这类占位文案")
        ctx.close()

        # ---------------- 移动端 ----------------
        print("\n移动端")
        ctx = browser.new_context(viewport={"width": 390, "height": 844},
                                  is_mobile=True, has_touch=True, device_scale_factor=2)
        page = ctx.new_page()
        merrs = []
        page.on("pageerror", lambda e: merrs.append(str(e)))
        page.goto(base + "/works/", wait_until="load")
        page.wait_for_timeout(600)
        m = page.evaluate("""() => {
            const card = document.querySelector('.wk-card');
            return {
                vw: window.innerWidth,
                docW: document.documentElement.scrollWidth,
                cardW: card ? Math.round(card.getBoundingClientRect().width) : 0,
                navBottom: Math.round(document.querySelector('.site-nav').getBoundingClientRect().bottom),
                heroTop: Math.round(document.querySelector('.page-hero h1').getBoundingClientRect().top),
            };
        }""")
        check(m["docW"] <= m["vw"] + 1, "没有横向溢出",
              f"文档宽 {m['docW']} / 视口 {m['vw']}")
        check(m["cardW"] > m["vw"] * 0.8, "卡片堆成单栏并占满宽度",
              f"卡片宽 {m['cardW']}")
        check(m["heroTop"] >= m["navBottom"], "标题没被固定导航切掉",
              f"标题顶 {m['heroTop']} / 导航底 {m['navBottom']}")
        check(not merrs, "移动端无未捕获异常", "; ".join(merrs[:2]))
        page.screenshot(path=str(SHOTS / "works-mobile.png"), full_page=True)
        ctx.close()

        # ---------------- 空态 ----------------
        print("\n一件公开作品都没有时的空态")
        wipe()
        ctx = browser.new_context(viewport=vp)
        page = ctx.new_page()
        page.goto(base + "/works/", wait_until="load")
        page.wait_for_timeout(400)
        st = page.evaluate(WALL)
        check(st["empty"], "渲染了设计过的空态面板（不是一片空白）")
        check("新生指南" in st["emptyText"], "空态给出了下一步", )
        check(not st["tabs"], "空态不显示筛选条")
        page.screenshot(path=str(SHOTS / "works-empty.png"))
        ctx.close()

        browser.close()

    wipe()
    dev_account.ensure(level=4)

    print()
    if failures:
        print(f"{len(failures)} 项未通过：" + "、".join(failures))
        return 1
    print("作品墙契约全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
