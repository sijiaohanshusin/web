# -*- coding: utf-8 -*-
"""校验生产静态文件管线，在本地就把只会在线上暴露的问题挑出来。

为什么需要这个命令：
    开发环境 DEBUG=True 不走哈希存储，静态文件按原名直出，所以下面这几类
    问题在本地怎么点都不会出现，一上线就白屏或 404：

    1. ES module 的相对 import 没被改写 —— 浏览器去请求未加哈希的文件名。
       Django 默认关闭 support_js_module_import_aggregation，我们在
       config/storage.py 里显式打开了，这里验证它确实生效。
    2. 第三方库带 sourceMappingURL 注释但没收 .map 文件 —— collectstatic
       直接抛 ValueError 中断部署（lenis.min.js 踩过）。
    3. importmap 里的 URL 与实际产出的哈希文件名不一致。
    4. CSS 里 url() 指向不存在的资源（字体、图片改名后忘了同步）。

用法（在 app/ 目录下）：
    python manage.py check_static_pipeline

发布前应当跑一次；退出码非 0 表示有问题，可直接用在 CI 里。
命令只往临时目录写入，不会碰 STATIC_ROOT。
"""
import os
import posixpath
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import unquote, urldefrag

from django.conf import settings
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import HashedFilesMixin
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.test import Client, override_settings

PROD_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "config.storage.ESTAManifestStaticFilesStorage"},
}

# 需要出现在页面上、且必须指向哈希文件名的资源。
# (正则, 说明)；正则第 1 组是 URL。
EXPECTED_ASSETS = [
    (r'<link[^>]+href="([^"]*css/tokens\.[0-9a-f]{12}\.css)"', "tokens.css"),
    (r'<link[^>]+href="([^"]*css/core\.[0-9a-f]{12}\.css)"', "core.css"),
    (r'"three":\s*"([^"]+)"', "importmap: three"),
    (r'"three/addons/loaders/SVGLoader\.js":\s*"([^"]+)"', "importmap: SVGLoader"),
    # 分镜 01 靠这条 importmap 解析 import("esta/logo-3d")，缺了就只剩 SVG 兜底
    (r'"esta/logo-3d":\s*"([^"]+)"', "importmap: esta/logo-3d"),
    (r'src="([^"]*vendor/gsap\.min\.[0-9a-f]{12}\.js)"', "gsap"),
    (r'src="([^"]*vendor/ScrollTrigger\.min\.[0-9a-f]{12}\.js)"', "ScrollTrigger"),
    (r'src="([^"]*vendor/lenis\.min\.[0-9a-f]{12}\.js)"', "lenis"),
    (r'src="([^"]*js/motion-core\.[0-9a-f]{12}\.js)"', "motion-core.js"),
    # 跨页转场的命名元素。它在 head 里同步加载（不能 defer，见 base.html），
    # 404 时转场静默退回整页淡入淡出、不报任何错 —— 只有这里能提前发现。
    (r'src="([^"]*js/view-transitions\.[0-9a-f]{12}\.js)"', "view-transitions.js"),
]


class Command(BaseCommand):
    help = "在临时目录跑一遍生产静态管线，校验哈希改写、importmap 与资源可达性"

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep", action="store_true",
            help="保留临时的 STATIC_ROOT 目录（排查时用，会打印路径）",
        )

    def handle(self, *args, **options):
        tmp = Path(tempfile.mkdtemp(prefix="esta-staticcheck-"))
        self.failures = []
        try:
            with override_settings(DEBUG=False, STATIC_ROOT=tmp, STORAGES=PROD_STORAGES):
                self._check_css_refs()
                self._collect(tmp)
                self._check_js_modules(tmp)
                self._check_page(tmp)
        finally:
            if options["keep"]:
                self.stdout.write(f"\n临时 STATIC_ROOT 保留在：{tmp}")
            else:
                shutil.rmtree(tmp, ignore_errors=True)

        if self.failures:
            raise CommandError(
                f"{len(self.failures)} 项未通过：" + "、".join(self.failures)
            )
        self.stdout.write(self.style.SUCCESS("\n生产静态管线校验通过"))

    # ------------------------------------------------------------------ 工具

    def _ok(self, label, detail=""):
        self.stdout.write(f"  {self.style.SUCCESS('OK')}   {label}" + (f"  {detail}" if detail else ""))

    def _fail(self, label, detail=""):
        self.failures.append(label)
        self.stdout.write(f"  {self.style.ERROR('FAIL')} {label}" + (f"  {detail}" if detail else ""))

    def _assert(self, cond, label, detail=""):
        (self._ok if cond else self._fail)(label, detail)

    # ------------------------------------------------------------------ 步骤

    def _check_css_refs(self):
        """用 Django 自己那两条 CSS 正则扫一遍全部样式表，逐个确认引用的目标真的存在。

        **为什么不能只靠下面那步 collectstatic**：Win32 API 会**默默丢掉路径末尾的
        点**。所以注释里一句 `url('...')` 这样的示例写法（正则会把 `...` 当成路径
        抓出来），在本机 `os.path.exists("css/...")` 等于问 `css/` 这个目录存不存在
        —— True。Django 那条「找不到就 raise ValueError」的分支根本走不到，接着
        `self.open()` 打开目录抛 OSError，又正好被 `except OSError: return name`
        吞掉。于是本机 collectstatic 一路绿灯。

        到了 Linux 上，`css/...` 就是一个不存在的文件名：collectstatic 抛
        ValueError → entrypoint 里那一步失败 → 容器起不来 → 线上 502。
        **真踩过一次**（`--scope-art` 那条注释）。

        所以这一步刻意**不碰文件系统**：先把 finders 能列出来的静态路径收成一个
        字符串集合，再拿引用去查集合。纯字符串比较，没有平台差异。
        """
        self.stdout.write("CSS 引用的目标真实存在（不查文件系统，查 finders 的清单）")
        known = set()
        for finder in finders.get_finders():
            for path, _storage in finder.list([]):
                known.add(path.replace(os.sep, "/"))
        self._assert(len(known) > 50, "finders 真的列出了静态文件（不然这一步空跑）",
                     f"{len(known)} 个")

        css_pats = [
            re.compile(p[0] if isinstance(p, tuple) else p, re.IGNORECASE)
            for ext, pats in HashedFilesMixin.patterns if ext == "*.css"
            for p in pats
            # sourceMappingURL 那条由 collectstatic 自己管（它抓的是注释里的 map 文件）
            if "sourceMappingURL" not in (p[0] if isinstance(p, tuple) else p)
        ]
        self._assert(len(css_pats) >= 2, "取到了 Django 的 CSS 引用正则", f"{len(css_pats)} 条")

        bad = []
        checked = 0
        for name in sorted(n for n in known if n.endswith(".css")):
            abs_path = finders.find(name)
            if not abs_path:
                continue
            text = Path(abs_path).read_text(encoding="utf-8", errors="replace")
            for rx in css_pats:
                for m in rx.finditer(text):
                    raw = (m.groupdict().get("url") or "").strip()
                    if not raw or raw.startswith(("#", "http:", "https:", "//", "data:")):
                        continue
                    target, _frag = urldefrag(unquote(raw))
                    target = target.split("?")[0]
                    if not target:
                        continue
                    if target.startswith("/"):
                        if not target.startswith(settings.STATIC_URL):
                            continue
                        rel = target.removeprefix(settings.STATIC_URL)
                    else:
                        rel = posixpath.join(posixpath.dirname(name), target)
                    rel = posixpath.normpath(rel)
                    checked += 1
                    if rel not in known:
                        bad.append(f"{name} → {raw}")

        self._assert(checked > 0, "确实扫到了 CSS 引用（不然这一步空跑）", f"{checked} 处")
        if bad:
            self._fail("**每条 CSS 引用都指向真实文件**",
                       "断链：" + "；".join(bad[:6]) +
                       "（注释里也不许出现示例写法，正则连注释一起扫）")
        else:
            self._ok("**每条 CSS 引用都指向真实文件**", f"{checked} 处全部命中")

    def _collect(self, tmp: Path):
        self.stdout.write("collectstatic（ManifestStaticFilesStorage）")
        # 任何 CSS url() 或 JS 相对 import 断链都会在这一步抛异常
        call_command("collectstatic", "--noinput", verbosity=0)
        manifest = tmp / "staticfiles.json"
        self._assert(manifest.exists(), "生成 staticfiles.json")
        self._ok("解析全部 CSS url() 与 JS import 无断链")

    def _check_js_modules(self, tmp: Path):
        """ES module 的相对 import 必须被改写成哈希名，裸标识符必须保持原样。"""
        self.stdout.write("ES module 路径改写")
        vendor = tmp / "vendor"

        mods = list(vendor.glob("three.module.min.*.js"))
        if not mods:
            self._fail("找到 three.module 的哈希产物")
            return
        text = mods[0].read_text(encoding="utf-8")
        # 改写后的形式是 from "./x.js"（Django 的替换模板会补一个空格）
        ref = re.search(r'from\s*["\'](\./three\.core[^"\']*)["\']', text)
        if not ref:
            self._fail("three.module 内部引用 three.core", "没找到引用，three 版本结构可能变了")
            return
        url = ref.group(1)
        self._assert(
            bool(re.search(r"three\.core\.min\.[0-9a-f]{12}\.js", url)),
            "three.module 的相对 import 已改写为哈希名", url,
        )
        self._assert((vendor / url.lstrip("./")).exists(), "改写后的目标文件真实存在")

        loaders = list(vendor.glob("SVGLoader.*.js"))
        if loaders:
            self._assert(
                re.search(r"from\s*['\"]three['\"]", loaders[0].read_text(encoding="utf-8")) is not None,
                "SVGLoader 的裸标识符 three 未被改写（交给 importmap）",
            )

        # 动态 import 的裸标识符。Django 那条正则不像静态形式那样限定 [./] 开头，
        # 会把 import("esta/logo-3d") 当相对路径去找文件、找不到就中断部署；
        # config/storage.py 覆盖掉了这个行为，这里守住它。
        scenes = list((tmp / "js" / "scenes").glob("logo-forge.*.js"))
        if not scenes:
            self._fail("找到 logo-forge 分镜的哈希产物")
        else:
            src = scenes[0].read_text(encoding="utf-8")
            self._assert(
                'import("esta/logo-3d")' in src,
                "动态 import 的裸标识符未被改写（交给 importmap）",
            )

    def _check_page(self, tmp: Path):
        """渲染首页，核对每个动效资源都指向哈希 URL 且文件真实存在。"""
        self.stdout.write("页面资源引用")
        body = Client().get("/").content.decode()

        for pattern, label in EXPECTED_ASSETS:
            m = re.search(pattern, body)
            if not m:
                self._fail(label, "页面里找不到（或未使用哈希文件名）")
                continue
            url = m.group(1)
            disk = tmp / url.replace("/static/", "").lstrip("/")
            self._assert(disk.exists(), label, url)

        im = body.find('type="importmap"')
        first_module = body.find('type="module"')
        self._assert(
            im != -1 and (first_module == -1 or im < first_module),
            "importmap 出现在所有 module 脚本之前",
        )

        def pos(fragment):
            m = re.search(r'src="[^"]*' + re.escape(fragment) + r'[^"]*"', body)
            return m.start() if m else -1

        self._assert(
            -1 < pos("gsap.min") < pos("ScrollTrigger.min") < pos("motion-core")
            and -1 < pos("lenis.min") < pos("motion-core"),
            "脚本顺序：gsap → ScrollTrigger → lenis → motion-core",
        )
        self._assert("site.css" not in body, "已无对已删除的 site.css 的引用")
