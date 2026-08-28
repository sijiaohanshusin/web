# -*- coding: utf-8 -*-
"""浏览器截图与运行时诊断工具。

补的是开发流程里最大的一个洞：改完前端只能靠推理，看不到真实渲染，也拿不到
控制台报错。有了它，「改 → 看 → 修」才闭得上环。

依赖：playwright（仅开发用，不要写进 app/requirements.txt）
    python -m pip install playwright
    python -m playwright install chromium

常用姿势
--------
    # 默认页面集，桌面 + 移动各来一张全页图
    python scripts/shoot.py

    # 单页
    python scripts/shoot.py --url /recruitment/

    # 只截某个元素（调组件时最省眼力）
    python scripts/shoot.py --url / --selector "#nf-hero"

    # 首页按 <section> 逐块出图（本项目一屏一分镜，这个模式最好用）
    python scripts/shoot.py --url / --sections

    # 直接看一个本地文件（SVG / HTML 片段都行）
    python scripts/shoot.py --file app/static/brand/logo-mark.svg

    # 滚到底再截，用来触发 ScrollTrigger 类动效
    python scripts/shoot.py --url / --scroll

    # 模拟无障碍偏好，验证降级路径
    python scripts/shoot.py --url / --reduced-motion

    # 在页面里求值，拿运行时状态
    python scripts/shoot.py --url / --eval "ESTA.motion.caps"

输出
----
图片写到仓库根的 .shots/（已在 .gitignore 里）。每次运行都会打印一份诊断：
HTTP 状态、控制台报错、未捕获异常、加载失败的资源。**控制台那一段比图片更
重要**，动效失效大多先在那里露头。

不传 --base-url 时脚本自己起一个 Django 开发服务器（端口 8799）并在结束时
关掉，不会干扰你手动开的 runserver。
"""
import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "app"
SHOTS = REPO / ".shots"
PORT = 8799

# 默认巡检的页面：招新主链路 + 会员内容页
DEFAULT_PAGES = [
    ("/", "home"),
    ("/recruitment/", "recruitment"),
    ("/recruit/", "guide"),
    ("/accounts/register/", "register-choice"),
    ("/accounts/login/", "login"),
    ("/news/", "news"),
    ("/events/", "events"),
    ("/files/", "files"),
]

DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.35)
        return s.connect_ex(("127.0.0.1", port)) == 0


class DevServer:
    """按需拉起 Django 开发服务器，退出时收拾干净。"""

    def __init__(self, port: int):
        self.port = port
        self.proc = None
        self.log = None

    def __enter__(self):
        if port_open(self.port):
            print(f"复用已在 {self.port} 端口监听的服务")
            return self
        env = dict(os.environ)
        # 关掉 B 站取数：dev 是 LocMem 缓存，每次新进程都冷启，首页要同步
        # 等三个外部接口，赶上限流就是 6 秒超时 ×3，把截图循环拖死。
        # 需要真实取数时自己设 BILIBILI_API_ENABLED=1 再跑。
        env.setdefault("BILIBILI_API_ENABLED", "0")
        # 日志必须落文件，不能用 PIPE。runserver 把每条请求日志写 stderr，
        # 一个页面就是几十行；PIPE 没人读，写满 64KB 内核缓冲后服务器卡在
        # write 上再也不响应 —— 表现为第三次 page.goto 直接超时，非常难查。
        SHOTS.mkdir(exist_ok=True)
        self.log = open(SHOTS / "devserver.log", "w+", encoding="utf-8", errors="replace")
        self.proc = subprocess.Popen(
            [sys.executable, "manage.py", "runserver", f"127.0.0.1:{self.port}", "--noreload"],
            cwd=APP, stdout=subprocess.DEVNULL, stderr=self.log, env=env,
        )
        for _ in range(80):
            if port_open(self.port):
                return self
            if self.proc.poll() is not None:
                raise SystemExit(f"开发服务器启动失败：\n{self._tail()}")
            time.sleep(0.25)
        raise SystemExit("开发服务器 20 秒内没起来")

    def _tail(self, n: int = 1500) -> str:
        if not self.log:
            return ""
        self.log.flush()
        return Path(self.log.name).read_text(encoding="utf-8", errors="replace")[-n:]

    def __exit__(self, *exc):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.log:
            self.log.close()
            self.log = None


class StaticServer:
    """把一个目录用 HTTP 供出来。

    ES module 有同源要求，file:// 下 import 会被 CORS 直接拒绝（真实踩过：
    3D 会标预览页在 file:// 下整页报 ERR_FAILED）。预览类页面一律走这个。
    """

    def __init__(self, directory: Path, port: int):
        self.directory = Path(directory).resolve()
        self.port = port
        self.httpd = None
        self.thread = None

    def __enter__(self):
        import functools
        import http.server
        import socketserver
        import threading

        handler = functools.partial(
            http.server.SimpleHTTPRequestHandler, directory=str(self.directory)
        )

        class Quiet(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

            def handle_error(self, request, client_address):
                pass  # 浏览器提前断开连接是常态，不必刷栈

        handler.log_message = lambda *a, **k: None
        self.httpd = Quiet(("127.0.0.1", self.port), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        print(f"静态服务 {self.directory} → http://127.0.0.1:{self.port}")
        return self

    def __exit__(self, *exc):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()


class PageProbe:
    """挂在 page 上收集诊断信息。"""

    def __init__(self, page):
        self.console = []
        self.errors = []
        self.failed = []
        page.on("console", self._console)
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.on("requestfailed", lambda r: self.failed.append(
            f"{r.method} {r.url} — {r.failure}"))
        page.on("response", self._response)

    def _console(self, msg):
        if msg.type in ("error", "warning"):
            self.console.append(f"[{msg.type}] {msg.text}")

    def _response(self, resp):
        if resp.status >= 400:
            self.failed.append(f"HTTP {resp.status} {resp.url}")

    def report(self, indent="  "):
        lines = []
        if self.errors:
            lines.append(f"{indent}未捕获异常 {len(self.errors)} 条:")
            lines += [f"{indent}  ! {e}" for e in self.errors[:6]]
        if self.failed:
            lines.append(f"{indent}资源失败 {len(self.failed)} 条:")
            lines += [f"{indent}  ! {f}" for f in self.failed[:8]]
        if self.console:
            lines.append(f"{indent}控制台 {len(self.console)} 条:")
            lines += [f"{indent}  · {c[:160]}" for c in self.console[:8]]
        if not lines:
            lines.append(f"{indent}控制台干净，无失败资源")
        return "\n".join(lines)

    @property
    def clean(self):
        return not (self.errors or self.failed)


def settle(page, scroll: bool, extra_wait: int, scroll_to: str | None = None):
    """等页面稳定：字体就绪 + 可选滚动 + 额外等待。"""
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    page.evaluate("() => document.fonts && document.fonts.ready")

    if scroll_to:
        # 数字当像素，其余当选择器。滚动后多等一会儿：Lenis 是平滑滚动，
        # 立刻截图会拍到运动中间态；固定导航的反色也需要一帧才切。
        if re.fullmatch(r"\d+", scroll_to):
            page.evaluate(f"() => window.scrollTo(0, {scroll_to})")
        else:
            page.evaluate(
                """(sel) => {
                    const el = document.querySelector(sel);
                    if (!el) throw new Error('找不到 ' + sel);
                    window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY + 8);
                }""",
                scroll_to,
            )
        page.wait_for_timeout(1400)

    if scroll:
        page.evaluate(
            """async () => {
                const step = Math.round(innerHeight * 0.6);
                const total = document.body.scrollHeight;
                for (let y = 0; y < total; y += step) {
                    scrollTo(0, y);
                    await new Promise(r => setTimeout(r, 220));
                }
                scrollTo(0, 0);
                await new Promise(r => setTimeout(r, 420));
            }"""
        )
    if extra_wait:
        page.wait_for_timeout(extra_wait)


def do_login(ctx, base, credentials: str) -> None:
    """走一遍真实登录表单，把会话 cookie 留在 context 里。

    刻意不去伪造 session cookie：那样会绕过登录视图，一旦登录链路本身出问题
    截图反而看不出来。走表单虽然慢一点，但截的是真实登录后的页面。
    """
    user, _, password = credentials.partition(":")
    page = ctx.new_page()
    page.goto(base.rstrip("/") + "/accounts/login/", wait_until="domcontentloaded")
    page.fill("input[name=username]", user)
    page.fill("input[name=password]", password)
    page.click("form button[type=submit], form input[type=submit]")
    page.wait_for_load_state("domcontentloaded")
    still_on_login = "/accounts/login" in page.url
    page.close()
    if still_on_login:
        raise SystemExit(
            f"登录失败：{user} 没能通过。先跑 python scripts/dev_account.py 创建账号。"
        )
    print(f"已登录 {user}")


def shoot_page(ctx, url, slug, label, args):
    page = ctx.new_page()
    probe = PageProbe(page)
    resp = page.goto(url, wait_until="domcontentloaded", timeout=25000)
    status = resp.status if resp else "?"
    if args.at is not None:
        # 抓拍模式：只等指定毫秒，不等 networkidle / 字体，否则等待本身
        # 就把要拍的动画等过去了
        page.wait_for_timeout(args.at)
    else:
        settle(page, args.scroll, args.wait, args.scroll_to)

    # --setup 在截图**之前**跑，用来把页面摆成想拍的那一态（展开折叠菜单、
    # 打开汉堡、给某个元素加类……）。
    # 和 --eval 分开是必要的：--eval 是「拍完之后取运行时状态」，它在截图之后
    # 才执行，用它去 click 一个菜单，图上什么都不会变 —— 而且看不出来是顺序问题。
    if args.setup:
        try:
            page.evaluate(f"() => {{ {args.setup} }}")
            page.wait_for_timeout(args.wait or 260)
        except Exception as e:
            print(f"  --setup 执行失败：{e}")

    out = []
    if args.sections:
        blocks = page.query_selector_all("section, .nf-hero, footer.site-footer")
        for i, el in enumerate(blocks):
            box = el.bounding_box()
            if not box or box["height"] < 40:
                continue
            path = SHOTS / f"{slug}--{label}--sec{i:02d}.png"
            el.scroll_into_view_if_needed()
            page.wait_for_timeout(args.wait or 260)
            el.screenshot(path=str(path))
            out.append(path)
    elif args.selector:
        el = page.query_selector(args.selector)
        if not el:
            print(f"  找不到选择器 {args.selector}")
        else:
            path = SHOTS / f"{slug}--{label}--el.png"
            el.screenshot(path=str(path))
            out.append(path)
    else:
        path = SHOTS / f"{slug}--{label}.png"
        page.screenshot(path=str(path), full_page=not args.viewport_only)
        out.append(path)

    evaluated = None
    if args.eval:
        try:
            evaluated = page.evaluate(f"() => {{ const v = ({args.eval}); "
                                      "return typeof v === 'undefined' ? '<undefined>' : v; }")
        except Exception as e:
            evaluated = f"<求值失败: {e}>"

    title = page.title()
    page.close()
    return {"status": status, "title": title, "probe": probe, "shots": out, "eval": evaluated}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="截图与运行时诊断", formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", action="append", help="要截的路径，可重复；缺省用内置页面集")
    ap.add_argument("--file", help="改为打开本地文件（SVG/HTML）")
    ap.add_argument("--base-url", help="用已有服务而不是自己起 runserver")
    ap.add_argument("--serve", metavar="DIR",
                    help="用静态 HTTP 服务供出某个目录，而不是起 Django。"
                         "ES module 在 file:// 下会被 CORS 挡住，预览页必须走 HTTP")
    ap.add_argument("--selector", help="只截这个元素")
    ap.add_argument("--sections", action="store_true", help="逐个 <section> 出图")
    ap.add_argument("--mobile", action="store_true", help="只截移动端")
    ap.add_argument("--desktop", action="store_true", help="只截桌面")
    ap.add_argument("--viewport-only", action="store_true", help="只截首屏，不截全页")
    ap.add_argument("--scroll", action="store_true", help="先滚一遍再截，触发滚动动效")
    ap.add_argument("--scroll-to", help="滚到指定位置再截：CSS 选择器或像素数。"
                                       "验证 position:fixed 的导航栏在不同区块上的表现时用")
    ap.add_argument("--reduced-motion", action="store_true", help="模拟 prefers-reduced-motion")
    ap.add_argument("--dark", action="store_true", help="模拟 prefers-color-scheme: dark")
    ap.add_argument("--setup", metavar="JS",
                    help="截图**之前**在页面里跑一段 JS，把页面摆成想拍的那一态，"
                         "例如 --setup \"document.querySelector('details').open=true\"。"
                         "注意 --eval 是拍完之后才跑的，不能拿它做准备工作")
    ap.add_argument("--eval", help="截图之后在页面里求值并打印结果")
    ap.add_argument("--wait", type=int, default=600, help="额外等待毫秒，默认 600")
    ap.add_argument("--at", type=int, help="导航后第 N 毫秒抓拍，跳过所有等待。"
                                          "用来捕捉动画中间态（加载动画、入场、分镜过程）")
    ap.add_argument("--login", metavar="USER:PASS",
                    help="先走一遍登录表单再访问目标页。驾驶舱页面必须用它。"
                         "配套账号可用 python scripts/dev_account.py 创建")
    ap.add_argument("--keep", action="store_true", help="保留上次的图，默认清空 .shots")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    SHOTS.mkdir(exist_ok=True)
    if not args.keep:
        for old in SHOTS.glob("*.png"):
            old.unlink()

    viewports = []
    if args.mobile or not args.desktop:
        viewports.append(("mobile", MOBILE, True))
    if args.desktop or not args.mobile:
        viewports.append(("desktop", DESKTOP, False))
    if args.mobile and not args.desktop:
        viewports = [v for v in viewports if v[0] == "mobile"]
    if args.desktop and not args.mobile:
        viewports = [v for v in viewports if v[0] == "desktop"]

    if args.file:
        targets = [(Path(args.file).resolve().as_uri(), Path(args.file).stem)]
        server = None
    else:
        paths = [(u, re.sub(r"[^a-z0-9]+", "-", u.strip("/").lower()) or "home")
                 for u in (args.url or [])] or DEFAULT_PAGES
        server = True
        targets = paths

    all_clean = True

    def run(base):
        nonlocal all_clean
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                for label, vp, is_mobile in viewports:
                    ctx = browser.new_context(
                        viewport=vp,
                        device_scale_factor=2 if is_mobile else 1,
                        is_mobile=is_mobile,
                        has_touch=is_mobile,
                        reduced_motion="reduce" if args.reduced_motion else "no-preference",
                        color_scheme="dark" if args.dark else "light",
                    )
                    if args.login:
                        do_login(ctx, base, args.login)
                    for target, slug in targets:
                        url = target if "://" in target else base.rstrip("/") + target
                        r = shoot_page(ctx, url, slug, label, args)
                        flag = "OK  " if r["probe"].clean and r["status"] in (200, "?") else "注意"
                        print(f"\n{flag} [{label}] {url}  HTTP {r['status']}  «{r['title'][:44]}»")
                        for s in r["shots"]:
                            print(f"     图 {s.relative_to(REPO)}")
                        if r["eval"] is not None:
                            print("     求值 " + json.dumps(r["eval"], ensure_ascii=False)[:400])
                        print(r["probe"].report())
                        all_clean = all_clean and r["probe"].clean
                    ctx.close()
            finally:
                browser.close()

    if args.serve:
        with StaticServer(args.serve, PORT + 1):
            run(f"http://127.0.0.1:{PORT + 1}")
    elif args.file:
        run("")
    elif args.base_url:
        run(args.base_url)
    else:
        with DevServer(PORT):
            run(f"http://127.0.0.1:{PORT}")

    shots = sorted(SHOTS.glob("*.png"))
    total = sum(s.stat().st_size for s in shots) / 1024
    print(f"\n共 {len(shots)} 张图，{total:.0f} KB，在 {SHOTS.relative_to(REPO)}/")
    if not all_clean:
        print("有页面存在控制台报错或资源加载失败，先看上面的诊断")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
