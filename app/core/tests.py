import re
import re
from unittest import mock

import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import roles

from . import bilibili
from .models import Feedback, FeedbackReply, SITE_CONFIG_CACHE_KEY, SiteConfig

User = get_user_model()

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def make_png(name="p.png", size=(4, 3)):
    """生成一张真图给 ImageField 用。

    不要手写 base64 常量：`ImageField` 的表单校验会调 Pillow 的 `verify()`，
    它比 `Image.open()` 严格（会校验 CRC）。之前用一段网上抄的「1x1 PNG」
    base64，`Image.open` 读得出宽高、直接建模型也能存，但过表单就报
    「不是图片或者是已损坏的图片」—— 两种路径的严格程度不一样，很容易误判成
    代码有问题。用 Pillow 现画一张最省事。
    """
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, (13, 169, 205)).save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class SiteConfigCacheTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_formal_release_does_not_reuse_legacy_cached_config(self):
        SiteConfig.objects.update_or_create(
            pk=1,
            defaults={
                "recruit_qq_group": "1081376858",
                "beta_mode": False,
                "auto_approve": False,
            },
        )
        stale = SiteConfig(
            pk=1,
            recruit_qq_group="1015304209",
            beta_mode=True,
            auto_approve=True,
        )
        cache.set("core:site_config:v2", stale, 3600)

        config = SiteConfig.load()

        self.assertEqual(SITE_CONFIG_CACHE_KEY, "core:site_config:v3")
        self.assertEqual(config.recruit_qq_group, "1081376858")
        self.assertFalse(config.beta_mode)
        self.assertFalse(config.auto_approve)


class FeedbackTests(TestCase):
    def test_page_renders(self):
        resp = self.client.get(reverse("core:feedback"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "网站问题反馈")

    def test_ajax_submit_creates_record(self):
        resp = self.client.post(reverse("core:feedback"), {
            "content": "注册页验证码按钮在手机上显示不全",
            "page": "https://heuesta.cn/accounts/register/",
            "contact": "qq:12345",
        }, **AJAX, REMOTE_ADDR="10.1.0.1")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        fb = Feedback.objects.get()
        self.assertEqual(fb.status, Feedback.Status.PENDING)
        self.assertEqual(fb.contact, "qq:12345")
        self.assertIsNone(fb.user)

    def test_short_content_rejected(self):
        resp = self.client.post(reverse("core:feedback"), {"content": "卡了"}, **AJAX, REMOTE_ADDR="10.1.0.2")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_cooldown_throttles(self):
        payload = {"content": "第一次提交的反馈内容够长了"}
        self.client.post(reverse("core:feedback"), payload, **AJAX, REMOTE_ADDR="10.1.0.3")
        resp = self.client.post(reverse("core:feedback"), payload, **AJAX, REMOTE_ADDR="10.1.0.3")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("频繁", resp.json()["msg"])
        self.assertEqual(Feedback.objects.count(), 1)

    def test_logged_in_user_attached(self):
        user = User.objects.create_user(username="fbuser", password="x")
        user.set_level(roles.LEVEL_OFFICER)
        self.client.login(username="fbuser", password="x")
        self.client.post(reverse("core:feedback"), {"content": "登录用户提交的反馈内容"}, **AJAX, REMOTE_ADDR="10.1.0.4")
        self.assertEqual(Feedback.objects.get().user, user)


class FeedbackReplyTests(TestCase):
    def setUp(self):
        self.submitter = User.objects.create_user(username="sub", password="x")
        self.submitter.set_level(roles.LEVEL_APPLICANT)
        self.other = User.objects.create_user(username="other", password="x")
        self.other.set_level(roles.LEVEL_APPLICANT)
        self.officer = User.objects.create_user(username="off2", password="x")
        self.officer.set_level(roles.LEVEL_OFFICER)
        self.fb = Feedback.objects.create(user=self.submitter, content="论坛链接希望新标签页打开")

    def url(self):
        return reverse("core:feedback_detail", args=[self.fb.pk])

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(self.url())
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_unrelated_user_forbidden(self):
        self.client.login(username="other", password="x")
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_submitter_can_view_and_reply(self):
        self.client.login(username="sub", password="x")
        self.assertEqual(self.client.get(self.url()).status_code, 200)
        self.client.post(self.url(), {"content": "补充：手机端也一样"})
        self.assertEqual(self.fb.replies.count(), 1)

    def test_officer_can_reply(self):
        self.client.login(username="off2", password="x")
        self.client.post(self.url(), {"content": "已修复，请刷新后再试"})
        reply = self.fb.replies.get()
        self.assertEqual(reply.author, self.officer)

    def test_submitter_reply_reopens_resolved(self):
        self.fb.status = Feedback.Status.RESOLVED
        self.fb.save(update_fields=["status"])
        self.client.login(username="sub", password="x")
        self.client.post(self.url(), {"content": "还是有问题，麻烦再看看"})
        self.fb.refresh_from_db()
        self.assertEqual(self.fb.status, Feedback.Status.PENDING)

    def test_officer_reply_does_not_reopen(self):
        self.fb.status = Feedback.Status.RESOLVED
        self.fb.save(update_fields=["status"])
        self.client.login(username="off2", password="x")
        self.client.post(self.url(), {"content": "此问题已在 v1.1 修复"})
        self.fb.refresh_from_db()
        self.assertEqual(self.fb.status, Feedback.Status.RESOLVED)


class FeedbackDashboardTests(TestCase):
    def setUp(self):
        self.officer = User.objects.create_user(username="off", password="x")
        self.officer.set_level(roles.LEVEL_OFFICER)
        self.fb = Feedback.objects.create(content="测试反馈内容", contact="qq:1")

    def test_anonymous_redirected(self):
        resp = self.client.get(reverse("dashboard:feedbacks"))
        self.assertEqual(resp.status_code, 302)

    def test_officer_sees_list(self):
        self.client.login(username="off", password="x")
        resp = self.client.get(reverse("dashboard:feedbacks"))
        self.assertContains(resp, "测试反馈内容")

    def test_resolve_flow(self):
        self.client.login(username="off", password="x")
        self.client.post(reverse("dashboard:feedbacks"), {
            "action": "resolve", "id": self.fb.pk, "note": "已修复",
        })
        self.fb.refresh_from_db()
        self.assertEqual(self.fb.status, Feedback.Status.RESOLVED)
        self.assertEqual(self.fb.admin_note, "已修复")
        self.assertEqual(self.fb.resolved_by, self.officer)


class BilibiliRequestHeaderTests(TestCase):
    """B 站取数的请求头契约与降级路径。

    2026-08 线上事故：首页精选视频封面长期为空，app 日志 48 小时刷了 40 条
    412。原因是请求头带了 Referer: https://www.bilibili.com/ —— 浏览器 UA
    加站内 Referer 却没有 buvid/WBI 签名，被判定为伪装浏览器。这几个用例把
    "不发 Referer""不用 requests 默认 UA"钉死，避免后人顺手加回去。
    """

    def setUp(self):
        cache.clear()

    def test_headers_carry_no_referer(self):
        self.assertNotIn("Referer", bilibili.HEADERS)
        self.assertNotIn("referer", {k.lower() for k in bilibili.HEADERS})

    def test_user_agent_is_self_identifying(self):
        ua = bilibili.HEADERS["User-Agent"]
        self.assertIn("heuesta.cn", ua)
        self.assertNotIn("python-requests", ua)
        # 不假装浏览器：伪装 UA 正是触发风控的那一半原因
        self.assertNotIn("Mozilla", ua)

    @override_settings(BILIBILI_API_ENABLED=True)
    def test_request_sends_expected_headers(self):
        with mock.patch("core.bilibili.requests.get") as get:
            get.return_value = mock.Mock(
                status_code=200,
                json=mock.Mock(return_value={"code": 0, "data": {"title": "标题", "pic": "http://i0.hdslb.com/a.jpg"}}),
            )
            bilibili.get_video_info("BV1AhnGzVEsD")

        sent = get.call_args.kwargs["headers"]
        self.assertEqual(sent, bilibili.HEADERS)
        self.assertEqual(get.call_args.kwargs["timeout"], bilibili.API_TIMEOUT)

    @override_settings(BILIBILI_API_ENABLED=True)
    def test_video_info_parses_and_upgrades_cover_to_https(self):
        with mock.patch("core.bilibili.requests.get") as get:
            get.return_value = mock.Mock(
                status_code=200,
                json=mock.Mock(return_value={"code": 0, "data": {
                    "title": "电子科技协会招新宣传视频",
                    "pic": "http://i0.hdslb.com/bfs/archive/cover.jpg",
                    "duration": 95,
                    "stat": {"view": 23456},
                }}),
            )
            info = bilibili.get_video_info("BV1AhnGzVEsD")

        self.assertEqual(info["title"], "电子科技协会招新宣传视频")
        self.assertTrue(info["pic"].startswith("https://"))
        self.assertEqual(info["duration"], "1:35")
        self.assertEqual(info["view"], "2.3万")

    @override_settings(BILIBILI_API_ENABLED=True)
    def test_412_degrades_without_raising_and_negative_caches(self):
        with mock.patch("core.bilibili.requests.get") as get:
            get.return_value = mock.Mock(status_code=412, json=mock.Mock(return_value={}))
            with self.assertLogs("core.bilibili", level="WARNING") as logs:
                first = bilibili.get_video_info("BV1AhnGzVEsD")
            # 命中失败短缓存，不再打第二次请求
            second = bilibili.get_video_info("BV1AhnGzVEsD")

        self.assertIsNone(first)
        self.assertIsNone(second)
        self.assertEqual(get.call_count, 1)
        self.assertIn("412", logs.output[0])
        # 风控是可预期状态，日志里不该出现堆栈
        self.assertNotIn("Traceback", "\n".join(logs.output))

    @override_settings(BILIBILI_API_ENABLED=True)
    def test_network_error_degrades(self):
        with mock.patch("core.bilibili.requests.get", side_effect=requests.ConnectionError("boom")):
            with self.assertLogs("core.bilibili", level="WARNING"):
                self.assertIsNone(bilibili.get_stats("70859324"))
                self.assertEqual(bilibili.get_latest_videos("70859324"), [])

    @override_settings(BILIBILI_API_ENABLED=False)
    def test_kill_switch_skips_network_entirely(self):
        with mock.patch("core.bilibili.requests.get") as get:
            self.assertIsNone(bilibili.get_video_info("BV1AhnGzVEsD"))
            self.assertIsNone(bilibili.get_stats("70859324"))
            self.assertEqual(bilibili.get_latest_videos("70859324"), [])
        get.assert_not_called()


class HomePageDegradationTests(TestCase):
    """B 站接口挂掉时首页必须照常渲染。"""

    def setUp(self):
        cache.clear()

    @override_settings(BILIBILI_API_ENABLED=True)
    def test_home_renders_when_bilibili_is_blocked(self):
        with mock.patch("core.bilibili.requests.get") as get:
            get.return_value = mock.Mock(status_code=412, json=mock.Mock(return_value={}))
            resp = self.client.get(reverse("core:home"))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "焊接每一个")
        # 取不到视频时精选区整块隐藏，不留空壳
        self.assertNotContains(resp, "精选培训视频")


class HomeAccessCopyTests(TestCase):
    def test_home_does_not_promise_all_resources_after_registration(self):
        for level in (None, 1, 2, 3):
            with self.subTest(level=level):
                self.client.logout()
                if level is not None:
                    member = User.objects.create_user(username=f"copy-check-{level}", member_level=level)
                    self.client.force_login(member)
                response = self.client.get(reverse("core:home"))
                self.assertNotContains(response, "注册会员解锁全部内容")
                self.assertContains(response, "按会员等级开放，具体以资料页权限为准")
                if level in (None, 1):
                    self.assertContains(response, "公开版块可浏览，一面通过后可参与讨论；新用户发帖需审核")

    def test_deploy_check_follows_css_font_references_not_six_preloads(self):
        from pathlib import Path
        script = (Path(__file__).resolve().parents[2] / "ops" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn('tokens_css=$(curl', script)
        self.assertIn('<<<"$tokens_css"', script)
        self.assertIn('preload_count', script)
        self.assertNotIn('首页引用了 $n 个字体，应为 6', script)


class MotionPipelineTests(TestCase):
    """动效链路的模板接线。

    这些断言看着琐碎，但每一条对应一种「页面不报错、效果静默消失」的故障：
    脚本顺序反了 motion-core 拿不到 gsap；importmap 挪到 module 脚本后面就
    整个失效；home.css 漏加载首页直接散架。都是浏览器控制台不一定报错的那种。
    """

    def test_script_order_lets_motion_core_see_libraries(self):
        body = self.client.get(reverse("core:home")).content.decode()

        def pos(fragment):
            index = body.find(fragment)
            self.assertNotEqual(index, -1, f"页面里找不到 {fragment}")
            return index

        # motion-core 直接读 window.gsap / window.Lenis，必须排在它们之后
        self.assertLess(pos("vendor/gsap"), pos("vendor/ScrollTrigger"))
        self.assertLess(pos("vendor/ScrollTrigger"), pos("js/motion-core"))
        self.assertLess(pos("vendor/lenis.min"), pos("js/motion-core"))

    def test_importmap_precedes_module_scripts(self):
        body = self.client.get(reverse("core:home")).content.decode()
        importmap = body.find('type="importmap"')
        self.assertNotEqual(importmap, -1)
        first_module = body.find('type="module"')
        if first_module != -1:
            self.assertLess(importmap, first_module, "importmap 必须在任何 module 脚本之前")

    def test_importmap_exposes_three_bare_specifiers(self):
        body = self.client.get(reverse("core:home")).content.decode()
        self.assertIn('"three":', body)
        self.assertIn('"three/addons/loaders/SVGLoader.js":', body)

    def test_home_loads_three_css_layers_inner_pages_load_two(self):
        home = self.client.get(reverse("core:home")).content.decode()
        for layer in ("css/tokens.css", "css/core.css", "css/home.css"):
            self.assertIn(layer, home)

        inner = self.client.get(reverse("news:list")).content.decode()
        self.assertIn("css/tokens.css", inner)
        self.assertIn("css/core.css", inner)
        # 首页分镜样式不该让内页付流量
        self.assertNotIn("css/home.css", inner)

    def test_no_reference_to_removed_stylesheet(self):
        for url in (reverse("core:home"), reverse("news:list"), reverse("accounts:login")):
            self.assertNotIn("site.css", self.client.get(url).content.decode(), url)

    def test_data_nav_zones_present_for_nav_inversion(self):
        """motion-core 靠 data-nav 切换导航反色，首页必须同时有 dark 与 light 区块。"""
        body = self.client.get(reverse("core:home")).content.decode()
        self.assertIn('data-nav="dark"', body)
        self.assertIn('data-nav="light"', body)


class BrandAssetTests(TestCase):
    """会标矢量与 inline_svg 标签。

    会标已从位图换成内联 SVG，几何只存在于 app/static/brand/logo-mark.svg
    这一份文件里。下面几条守住这个单一事实来源不被绕过。
    """

    def test_nav_and_footer_inline_the_svg_not_an_image(self):
        body = self.client.get(reverse("core:home")).content.decode()
        # 内联 SVG 才能让 currentColor 生效（白区反色靠它）
        self.assertIn('class="nav-logo"', body)
        self.assertIn('class="footer-logo"', body)
        self.assertIn('stroke="currentColor"', body)
        # 不该再有位图会标
        self.assertNotIn("img/logo-mark.png", body)

    def test_decorative_usage_is_hidden_from_screen_readers(self):
        """导航会标旁边就是「电子科技协会」文字，重复朗读只会吵。"""
        body = self.client.get(reverse("core:home")).content.decode()
        nav_svg = re.search(r'<svg[^>]*class="nav-logo"[^>]*>', body)
        self.assertIsNotNone(nav_svg, "找不到导航会标的 svg 开标签")
        tag = nav_svg.group(0)
        self.assertIn('aria-hidden="true"', tag)
        self.assertNotIn("aria-labelledby", tag)

    def test_no_duplicate_title_ids_when_inlined_multiple_times(self):
        """同一页内联多次不能产生重复 id（HTML 合法性 + 无障碍都会坏）。"""
        body = self.client.get(reverse("core:home")).content.decode()
        self.assertEqual(body.count('id="esta-logo-title"'), 0)

    def test_comments_are_stripped_from_inlined_output(self):
        """SVG 里的维护注释比图形本身还长，不该塞进每个页面。"""
        body = self.client.get(reverse("core:home")).content.decode()
        self.assertNotIn("Zhang-Suen", body)
        self.assertNotIn("annular ring", body)

    def test_svg_source_is_well_formed_xml(self):
        """独立 .svg 走 XML 解析，无值属性会让 three.js 的 SVGLoader 读不出东西。"""
        import xml.etree.ElementTree as ET
        from pathlib import Path

        from django.conf import settings

        path = Path(settings.BASE_DIR) / "static" / "brand" / "logo-mark.svg"
        ET.fromstring(path.read_text(encoding="utf-8"))  # 不合法会抛 ParseError

    def test_missing_file_fails_loudly(self):
        from django.template import Context, Template

        with self.assertRaises(ValueError):
            Template('{% load brand %}{% inline_svg "brand/nope.svg" %}').render(Context())


class PreloaderTests(TestCase):
    """开场加载动画的服务端接线。

    行为契约（进度、揭幕、兜底、reduced-motion）由 scripts/check_preloader.py
    在真实浏览器里验证。这里只守模板层：该出现的页面出现、不该出现的不出现。
    """

    def test_only_home_renders_the_overlay(self):
        home = self.client.get(reverse("core:home")).content.decode()
        self.assertIn('id="esta-preloader"', home)

        for name in ("news:list", "events:list", "accounts:login"):
            body = self.client.get(reverse(name)).content.decode()
            self.assertNotIn('id="esta-preloader"', body, name)

    def test_preloader_script_loads_before_motion_core_everywhere(self):
        """ESTA.preload 契约必须在任何页面都存在，且早于 motion-core。"""
        for name in ("core:home", "news:list"):
            body = self.client.get(reverse(name)).content.decode()
            pre = body.find("js/preloader")
            motion = body.find("js/motion-core")
            self.assertNotEqual(pre, -1, name)
            self.assertNotEqual(motion, -1, name)
            self.assertLess(pre, motion, name)

    def test_overlay_carries_its_own_critical_css(self):
        """遮罩必须自带内联样式，否则会先闪一帧无样式内容。"""
        home = self.client.get(reverse("core:home")).content.decode()
        overlay_at = home.find('id="esta-preloader"')
        style_at = home.find(".esta-pre {")
        self.assertNotEqual(style_at, -1, "没有找到内联 critical CSS")
        self.assertLess(style_at, overlay_at, "内联样式必须在遮罩标记之前")

    def test_css_failsafe_and_reduced_motion_rules_present(self):
        """两条救命规则：9 秒无条件收掉、reduced-motion 整块不显示。"""
        home = self.client.get(reverse("core:home")).content.decode()
        self.assertIn("esta-pre-failsafe", home)
        self.assertIn("prefers-reduced-motion", home)


class Logo3DWiringTests(TestCase):
    """3D 会标的服务端接线。

    3D 模块本身的行为契约由 scripts/check_logo3d.py 在真实浏览器里验证
    （几何来自 SVG、并联脉冲、显存释放）。这里只守 importmap ——
    它一错，浏览器就是一句 "Failed to resolve module specifier"，
    而模板渲染和测试都不会报错。
    """

    def test_importmap_exposes_three_and_addons(self):
        body = self.client.get(reverse("core:home")).content.decode()
        for spec in (
            '"three":',
            '"three/addons/loaders/SVGLoader.js":',
            '"three/addons/utils/BufferGeometryUtils.js":',
            '"esta/logo-3d":',
        ):
            self.assertIn(spec, body, f"importmap 缺少 {spec}")

    def test_importmap_targets_are_resolvable_static_paths(self):
        """每个映射目标都必须是 staticfiles 能找到的真实文件。"""
        from django.contrib.staticfiles import finders

        body = self.client.get(reverse("core:home")).content.decode()
        block = re.search(r'<script type="importmap">(.*?)</script>', body, re.S)
        self.assertIsNotNone(block, "找不到 importmap")

        targets = re.findall(r'"[^"]+":\s*"([^"]+)"', block.group(1))
        self.assertGreaterEqual(len(targets), 4)
        for url in targets:
            rel = url.replace("/static/", "", 1)
            self.assertIsNotNone(finders.find(rel), f"importmap 指向不存在的文件：{url}")

    def test_three_core_ships_alongside_module_build(self):
        """three.module.min.js 内部 import three.core.min.js，两个必须同时存在。"""
        from django.contrib.staticfiles import finders

        for name in ("vendor/three.module.min.js", "vendor/three.core.min.js"):
            self.assertIsNotNone(finders.find(name), f"缺少 {name}")

    def test_logo_svg_exposes_the_attributes_the_3d_module_reads(self):
        """3D 模块靠这些属性识别走线、焊盘与点亮顺序，删了就装配失败。"""
        from pathlib import Path

        from django.conf import settings

        svg = (Path(settings.BASE_DIR) / "static" / "brand" / "logo-mark.svg").read_text(
            encoding="utf-8"
        )
        self.assertEqual(svg.count('data-esta-trace="'), 3)
        self.assertEqual(svg.count('data-esta-pad="'), 3)
        self.assertEqual(svg.count('data-esta-order="'), 6)
        # 焊盘必须带 cx/cy/r：模块直接读原始属性，不从贝塞尔近似反推
        self.assertEqual(svg.count("<circle"), 3)


class ForgeSceneTests(TestCase):
    """分镜 01「会标是一块真的电路板」的服务端接线。

    分镜的运行时行为（sticky 钉住、五道工序按序点亮、reduced-motion 回落）
    由 scripts/check_forge.py 在真实浏览器里逐帧断言。这里只守模板侧那几件
    「删了不报错、效果直接消失」的事。
    """

    def setUp(self):
        self.body = self.client.get(reverse("core:home")).content.decode()

    def test_section_and_stage_anchors_exist(self):
        # check_forge.py 与 home.css 都按这两个 id 定位，改名要同步三处
        self.assertIn('id="nf-forge"', self.body)
        self.assertIn('id="nf-forge-stage"', self.body)
        self.assertIn("nf-forge-pin", self.body)

    def test_five_process_steps_are_present_and_ordered(self):
        """工序清单的 data-forge-step 顺序就是分镜的时间线顺序。"""
        steps = re.findall(r'data-forge-step="([^"]+)"', self.body)
        self.assertEqual(steps, ["substrate", "copper", "pads", "mask", "silk"])

    def test_stage_inlines_the_logo_as_geometry_source_and_fallback(self):
        """舞台里必须是内联 SVG，不能是 <img>。

        它一份两用：3D 没就位时是兜底显示，就位后又是 SVGLoader 的几何来源
        （所以不必再发一次请求）。换成 <img> 两个用途同时失效，而页面看着正常。
        """
        stage = self.body[self.body.find('id="nf-forge-stage"'):]
        stage = stage[: stage.find("</section>")]
        self.assertIn("nf-forge-fallback", stage)
        self.assertIn("<svg", stage)
        self.assertNotIn("<img", stage)
        self.assertIn('data-esta-logo="mark"', stage)

    def test_scene_module_is_loaded(self):
        self.assertIn("js/scenes/logo-forge.js", self.body)


class StaticStorageTests(TestCase):
    """守住 config.storage 对 Django 内部实现的两处耦合。

    ESTAManifestStaticFilesStorage 要放过动态 import 里的裸标识符，判据是
    Django 渲染这条正则时用的替换模板字符串。Django 一改，覆盖就悄悄失效、
    collectstatic 重新在部署时炸 —— 用测试把这个耦合钉住，升级时立刻知道。
    """

    def test_django_still_uses_the_dynamic_import_template_we_key_on(self):
        from django.contrib.staticfiles.storage import HashedFilesMixin

        from config.storage import ESTAManifestStaticFilesStorage

        _, patterns = HashedFilesMixin._js_module_import_aggregation_patterns
        templates = [p[1] for p in patterns if isinstance(p, (tuple, list))]
        self.assertIn(
            ESTAManifestStaticFilesStorage.DYNAMIC_IMPORT_TEMPLATE, templates,
            "Django 改了动态 import 的替换模板，config/storage.py 的判据要跟着改",
        )

    def test_bare_specifier_is_left_for_the_importmap(self):
        from config.storage import ESTAManifestStaticFilesStorage

        storage = ESTAManifestStaticFilesStorage()
        convert = storage.url_converter(
            "js/scenes/logo-forge.js", {},
            ESTAManifestStaticFilesStorage.DYNAMIC_IMPORT_TEMPLATE,
        )
        match = re.search(
            r'(?P<matched>import\(["\'](?P<url>.*?)["\']\))',
            'import("esta/logo-3d")',
        )
        self.assertEqual(convert(match), 'import("esta/logo-3d")')

    def test_relative_dynamic_import_to_a_missing_file_still_raises(self):
        """断链必须继续在部署前炸出来，这是打开改写开关的全部意义。"""
        from config.storage import ESTAManifestStaticFilesStorage

        storage = ESTAManifestStaticFilesStorage()
        convert = storage.url_converter(
            "js/scenes/logo-forge.js", {},
            ESTAManifestStaticFilesStorage.DYNAMIC_IMPORT_TEMPLATE,
        )
        match = re.search(
            r'(?P<matched>import\(["\'](?P<url>.*?)["\']\))',
            'import("./nope-does-not-exist.js")',
        )
        with self.assertRaises(ValueError):
            convert(match)


class SlotRegistryTests(TestCase):
    """登记表本身的自洽性，以及它和模板的一致性。

    素材槽的声明在 core/slots.py，使用在模板里。两边对不上时页面不会报错 ——
    那个位置只会一直显示占位框，和「还没拍」一模一样，没人会发现。所以这里
    扫描全部模板做双向比对。
    """

    def test_keys_are_well_formed_and_unique(self):
        from core import slots

        seen = set()
        for spec in slots.SLOTS:
            self.assertRegex(spec.key, slots.KEY_RE, f"{spec.key} 不符合 页面.区块.名字 的命名")
            self.assertNotIn(spec.key, seen, f"{spec.key} 重复登记")
            seen.add(spec.key)

    def test_every_spec_has_ratio_label_and_brief(self):
        """三样都不能省：比例占版面、名字给驾驶舱、要求给拍照的人。"""
        from core import slots

        for spec in slots.SLOTS:
            self.assertTrue(spec.label.strip(), f"{spec.key} 缺 label")
            self.assertRegex(spec.ratio, r"^\d+(\.\d+)?\s*/\s*\d+(\.\d+)?$", f"{spec.key} 的 ratio 不合法")
            self.assertGreater(len(spec.brief.strip()), 8, f"{spec.key} 的拍摄要求太短，等于没写")

    def test_fallback_files_exist(self):
        """兜底图必须真实存在，否则线上就是一个碎图图标。"""
        from django.contrib.staticfiles import finders

        from core import slots

        for spec in slots.SLOTS:
            if spec.fallback:
                self.assertIsNotNone(
                    finders.find(spec.fallback),
                    f"{spec.key} 的兜底图 {spec.fallback} 找不到",
                )

    def test_slot_keys_used_in_templates_are_all_registered(self):
        """模板里 {% slot "x" %} 的 x 必须都在登记表里。

        这一条替代了运行时抛异常：拼错的 key 在这里就被拦下，线上则走
        placeholder_spec 降级，不至于因为一个字母让整页 500。
        """
        import re as _re
        from pathlib import Path

        from django.conf import settings

        from core import slots

        used = set()
        for root in [Path(settings.BASE_DIR) / "templates"]:
            for path in root.rglob("*.html"):
                text = path.read_text(encoding="utf-8")
                # 先把 {% comment %} 块摘掉：注释里会写用法示例，那不是真的调用
                text = _re.sub(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", "", text, flags=_re.S)
                for m in _re.finditer(r'{%\s*slot\s+"([^"]+)"', text):
                    used.add(m.group(1))
        unknown = used - set(slots.REGISTRY)
        self.assertFalse(unknown, f"模板用了未登记的素材槽：{sorted(unknown)}")

    def test_gallery_view_keys_are_registered(self):
        """视图里那份顺序表同样要能对上登记表。"""
        from core import slots
        from core.views import GALLERY_SLOT_KEYS

        unknown = set(GALLERY_SLOT_KEYS) - set(slots.REGISTRY)
        self.assertFalse(unknown, f"GALLERY_SLOT_KEYS 里有未登记的 key：{sorted(unknown)}")


def an_empty_slot_key(kind="image"):
    """挑一个登记表里**确实还没有素材**的槽位，用来当空态的样本。

    刻意不写死某个 key。槽位会随着照片陆续到位被一个个填上，写死的话每补一张
    照片就有一批「空态长什么样」的断言变红 —— 而渲染逻辑一行都没动。真发生过：
    下面这些用例原本都拿 home.gallery.group 当样本，2024 年那张全员合影进仓库、
    在 slots.py 里加上 fallback 之后，五条断言同时红了。

    找不到样本时**报错而不是跳过**：空态是这套设计里正式的一态，得一直有东西
    在验它。真到了所有槽位都有素材的那天，就在这里造一个临时 SlotSpec。
    """
    from core import slots

    for spec in slots.SLOTS:
        if spec.kind == kind and not spec.fallback:
            return spec.key
    raise AssertionError(
        f"登记表里已经没有 kind={kind} 且没有 fallback 的槽位了，空态没有样本可测。"
        "要么在 slots.py 里留一个真的还缺素材的槽位，要么在这里造一个临时 SlotSpec。"
    )


class MediaSlotRenderTests(TestCase):
    """{% slot %} 的两种状态与缓存行为。"""

    # 有静态兜底图的样本。这个是写死的：它测的就是「登记表里的 fallback 会被
    # 渲染成图片」，哪天有人把 pcb 那条 fallback 删了，这里就**应该**红。
    FILLED_KEY = "home.gallery.pcb"

    def setUp(self):
        cache.clear()
        from core import slots

        self.empty_key = an_empty_slot_key()
        self.empty_spec = slots.get(self.empty_key)

    def _render(self, key, user=None):
        from django.template import Context, Template

        ctx = Context({"user": user})
        return Template('{%% load slots %%}{%% slot "%s" %%}' % key).render(ctx)

    def test_empty_slot_renders_the_designed_placeholder(self):
        from django.utils.html import escape

        html = self._render(self.empty_key)
        self.assertIn("slot is-empty", html)
        self.assertIn("slot-fid", html)                        # 四角定位标
        self.assertIn(escape(self.empty_spec.label), html)     # 名字
        self.assertIn(escape(self.empty_spec.brief), html)     # 拍摄要求原样显示
        self.assertNotIn("<img", html)                         # 绝不引一张不存在的图

    def test_empty_slot_reserves_layout_via_aspect_ratio(self):
        """占位与填好图必须占同样的版面，否则补图前后要排两次版。"""
        html = self._render(self.empty_key)
        self.assertIn(f"aspect-ratio: {self.empty_spec.ratio}", html)

    def test_slot_with_static_fallback_renders_an_image(self):
        html = self._render(self.FILLED_KEY)
        self.assertIn("slot is-filled", html)
        self.assertIn("img/carousel/pcb", html)

    def test_db_content_wins_over_static_fallback(self):
        from core.models import MediaSlot

        MediaSlot.objects.create(
            key="home.gallery.pcb",
            image=make_png("x.png", size=(1, 1)),
            alt="站务上传的板子", caption="现场拍的", credit="老王",
            focal_x=30, focal_y=70,
        )
        html = self._render("home.gallery.pcb")
        self.assertNotIn("img/carousel/pcb", html)
        self.assertIn("站务上传的板子", html)
        self.assertIn("现场拍的", html)
        self.assertIn("摄 / 老王", html)
        self.assertIn("object-position: 30% 70%", html)
        # 真实像素尺寸要写进属性，避免图片落地时把下面的内容顶一下
        self.assertIn('width="1"', html)
        self.assertIn('height="1"', html)

    def test_inactive_slot_falls_back_to_placeholder(self):
        from core.models import MediaSlot

        MediaSlot.objects.create(
            key=self.empty_key, image=make_png("y.png"), is_active=False,
        )
        html = self._render(self.empty_key)
        self.assertIn("slot is-empty", html)

    def test_upload_affordance_is_officer_only(self):
        """上传入口只给站务看，不要把内部流程摆在公开页面上。

        注意 data-slot-key 属性对所有人都在：它不是秘密，而是驾驶舱深链和
        自动化断言定位槽位用的钩子。这里管的是「可见的入口」。
        """
        officer = User.objects.create_user(username="off2", password="x")
        officer.member_level = 4
        officer.save()

        as_officer = self._render(self.empty_key, user=officer)
        as_visitor = self._render(self.empty_key, user=None)

        self.assertRegex(as_officer, r"slot-empty-(cta|key)")
        self.assertNotRegex(as_visitor, r"slot-empty-(cta|key)")

    def test_save_invalidates_the_cache(self):
        """MediaSlot 整表缓存，写入必须删键，否则站务上传完一小时看不到变化。"""
        from core.models import MEDIA_SLOT_CACHE_KEY, MediaSlot

        MediaSlot.load_all()
        self.assertIsNotNone(cache.get(MEDIA_SLOT_CACHE_KEY))

        obj = MediaSlot.objects.create(key="home.gallery.lab", image=make_png("z.png"))
        self.assertIsNone(cache.get(MEDIA_SLOT_CACHE_KEY))

        MediaSlot.load_all()
        obj.delete()
        self.assertIsNone(cache.get(MEDIA_SLOT_CACHE_KEY))

    def test_no_image_file_is_used_twice_on_the_home_page(self):
        """首页上同一个图片文件不许出现在两个分镜里。

        真发生过，而且是两处：`img/carousel/pcb.webp` 既硬编码在「3 个理由」那张
        549x686 的主图上、又是走廊第一格 `home.gallery.pcb` 的兜底；
        `img/carousel/etched-board.webp` 既在方向卡 03 上、又是 `home.gallery.etched`
        的兜底。而走廊被 `cloneNode` 复制过一份做无缝循环，所以那两个文件在**一屏
        首页**上各出现三次 —— 页面照常渲染、图也没碎，只是读起来像素材不够。

        判据拿渲染出来的 HTML 数：`{% static %}` 会带哈希名，所以不能拿源路径比。
        走廊那份克隆是 JS 在运行时做的，服务端 HTML 里每格只有一份，正好。
        """
        import re as _re

        body = self.client.get(reverse("core:home")).content.decode()
        srcs = _re.findall(r'<img[^>]+src="([^"]+\.(?:webp|png|jpe?g))"', body)
        self.assertGreater(len(srcs), 6, "首页图片太少，这条断言没测到东西")

        dupes = {s for s in srcs if srcs.count(s) > 1}
        self.assertFalse(
            dupes,
            "这些图片在首页上出现了不止一次 —— 换掉其中一处，别复用："
            f"{sorted(dupes)}",
        )

    def test_home_gallery_renders_every_declared_slot(self):
        body = self.client.get(reverse("core:home")).content.decode()
        from core.views import GALLERY_SLOT_KEYS

        # 只数走廊里的：页面上别处也有素材槽（影像区的片头循环），
        # 拿全页计数会随着新增槽位莫名其妙地失败
        strip = body[body.find('id="nf-strip-track"'):]
        strip = strip[: strip.find("</section>")]
        self.assertEqual(strip.count('class="slot '), len(GALLERY_SLOT_KEYS))
        # 每一格都要带着自己的 key：这是驾驶舱深链和自动化断言定位槽位的钩子，
        # 而且**填没填图都要有** —— 它原来只出现在空态里，于是给某个槽位补一张
        # 兜底图就会让「这一页用了哪几个槽位」的断言静默失效
        for key in GALLERY_SLOT_KEYS:
            self.assertIn(f'data-slot-key="{key}"', strip, f"走廊里没有 {key}")

    def test_filled_and_empty_slots_can_coexist(self):
        """真实照片与占位框必须能同时出现 —— 这正是旧轮播做不到的事：那一版整组
        要么全读数据库、要么全用静态图，补一张就得把六张一起补齐。

        刻意不拿首页走廊当样本。走廊六格现在全有素材了，那条「同时出现」的断言
        会随着「照片补齐」这件好事变红。这里把一填一空两格直接渲染在一起，钉的是
        渲染逻辑的性质，与当下有多少张照片无关。
        """
        html = self._render(self.FILLED_KEY) + self._render(self.empty_key)
        self.assertIn("slot is-filled", html)
        self.assertIn("slot is-empty", html)


def make_mp4(name="clip.mp4", size=2048):
    """一个「看起来像 mp4」的假文件。

    只用来验证渲染与校验分支，不需要真能解码 —— `FileField` 不像 `ImageField`
    那样会去解析内容，所以造一个带正确扩展名的字节串就够了。
    """
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, b"\x00\x00\x00\x18ftypmp42" + b"\x00" * size,
                              content_type="video/mp4")


class VideoSlotRenderTests(TestCase):
    """视频槽的渲染分支。

    核心设计：视频槽是图片槽的**超集**。同一个 `image` 字段在这里的身份是封面帧，
    所以「只上传了封面、片子还没剪好」是一个完整可用的状态，不需要为降级另备
    素材。这些测试就是在钉这条性质。
    """

    def setUp(self):
        cache.clear()
        self.key = "home.movie.teaser"

    def _render(self, key=None, **extra):
        from django.template import Context, Template

        args = " ".join(f'{k}={v}' for k, v in extra.items())
        return Template(
            '{%% load slots %%}{%% slot "%s" %s %%}' % (key or self.key, args)
        ).render(Context({"user": None}))

    def test_registry_marks_it_as_video(self):
        from core import slots

        self.assertEqual(slots.get(self.key).kind, slots.VIDEO)
        self.assertIn(self.key, slots.video_keys())

    def test_no_upload_renders_the_placeholder(self):
        html = self._render()
        self.assertIn("slot is-empty", html)
        self.assertNotIn("<video", html)

    def test_poster_only_degrades_to_a_plain_image(self):
        """片子还没剪好、只传了封面 —— 这是完整可用状态，不是半成品。"""
        from core.models import MediaSlot

        MediaSlot.objects.create(key=self.key, image=make_png("cover.png"), alt="片头封面")
        html = self._render()
        self.assertIn("slot is-filled", html)
        self.assertNotIn("<video", html)
        self.assertIn("片头封面", html)

    def test_video_renders_source_elements_with_poster(self):
        from core.models import MediaSlot

        MediaSlot.objects.create(
            key=self.key, image=make_png("cover.png"), alt="片头循环",
            video_mp4=make_mp4(), video_webm=make_mp4("clip.webm"),
        )
        html = self._render()
        self.assertIn("slot is-filled is-video", html)
        self.assertIn('type="video/webm"', html)
        self.assertIn('type="video/mp4"', html)
        self.assertIn("poster=", html)

    def test_webm_source_comes_before_mp4(self):
        """浏览器按顺序挑第一个能播的，webm 同画质更小，要排前面。"""
        from core.models import MediaSlot

        MediaSlot.objects.create(
            key=self.key, image=make_png("c.png"),
            video_mp4=make_mp4(), video_webm=make_mp4("c.webm"),
        )
        html = self._render()
        self.assertLess(html.index("video/webm"), html.index("video/mp4"))

    def test_video_element_has_no_autoplay_attribute(self):
        """自动播必须由 JS 按能力决定。

        写死 autoplay 就没法在 prefers-reduced-motion / 省流模式下不播 ——
        CSS 拦不住它，HTML 属性也没法条件化。
        """
        from core.models import MediaSlot

        MediaSlot.objects.create(key=self.key, image=make_png("c.png"), video_mp4=make_mp4())
        html = self._render()
        self.assertNotIn("autoplay", html)
        for attr in ("muted", "loop", "playsinline", 'preload="metadata"'):
            self.assertIn(attr, html)

    def test_image_slot_never_renders_video_even_with_files_attached(self):
        """登记表说这是图片槽，就算数据库里塞了视频也不该播。

        登记表是权威：哪个位置放什么由代码决定，不由数据库里恰好有什么决定。
        """
        from core.models import MediaSlot

        MediaSlot.objects.create(
            key="home.gallery.lab", image=make_png("l.png"), video_mp4=make_mp4(),
        )
        html = self._render("home.gallery.lab")
        self.assertNotIn("<video", html)
        self.assertIn("slot is-filled", html)

    def test_runtime_fallback_used_when_nothing_uploaded(self):
        """B 站封面这类运行时兜底：没有上传时用它，别显示占位框。"""
        html = self._render(fallback_url='"https://example.com/cover.jpg"')
        self.assertIn("https://example.com/cover.jpg", html)
        self.assertNotIn("slot is-empty", html)

    def test_static_fallback_beats_runtime_fallback(self):
        """静态兜底是仓库里钉死的自有素材，运行时兜底是碰运气拿到的。"""
        html = self._render("home.gallery.pcb",
                            fallback_url='"https://example.com/other.jpg"')
        self.assertIn("img/carousel/pcb", html)
        self.assertNotIn("example.com/other.jpg", html)

    def test_facade_on_home_page_uses_the_slot(self):
        body = self.client.get(reverse("core:home")).content.decode()
        facade = body[body.find('id="video-facade"'):]
        facade = facade[: facade.find("</section>")]
        self.assertIn("video-facade-media", facade)

    def test_video_controller_script_is_loaded_site_wide(self):
        """素材槽可以出现在任何页面，控制脚本必须全站都在。"""
        for url in (reverse("core:home"), reverse("news:list")):
            self.assertIn("js/video-slots.js", self.client.get(url).content.decode())


class HomeOpeningSceneTests(TestCase):
    """分镜 00「开场」与 02「数据」的接线。

    时序行为由 scripts/check_hero.py 在真实浏览器里断言（那些东西静态渲染看不
    出来）。这里只守「删了不报错、效果静默消失」的挂钩点。
    """

    def setUp(self):
        self.body = self.client.get(reverse("core:home")).content.decode()

    def test_hero_has_the_scope_scan_line(self):
        self.assertIn("nf-hero-scan", self.body)

    def test_data_scene_carries_the_dark_scope_grid(self):
        """示波器网格是分镜 02 的身份。掉了这个类它就退回一块普通黑区。"""
        self.assertRegex(self.body, r'class="[^"]*nf-scope[^"]*nf-bignum-section')

    def test_big_number_declares_a_delay_to_follow_the_sweep(self):
        """没有这个延迟，数字和扫描线同时开始，「扫过后定格」的叙事就没了。"""
        match = re.search(r'class="counter" data-target="\d+" data-delay="(\d+)"', self.body)
        self.assertIsNotNone(match, "大数字没有 data-delay")
        self.assertGreaterEqual(int(match.group(1)), 500)

    def test_preloader_lock_pauses_the_hero_reveal(self):
        """这条 CSS 是「揭幕接 Hero」的全部实现。

        删掉它页面不会报错、也不会白屏 —— 只是巨字的入场动画又变成在加载动画
        底下偷偷跑完，幕布升起时文字已经就位。没有任何可见故障，所以必须钉住。
        """
        from pathlib import Path

        from django.conf import settings

        css = (Path(settings.BASE_DIR) / "static" / "css" / "core.css").read_text(encoding="utf-8")
        self.assertRegex(
            css,
            r"html\.esta-pre-lock\s+\.line-reveal\s*\{[^}]*animation-play-state:\s*paused",
        )


class HomeDirectionAndRoadmapTests(TestCase):
    """分镜 03「方向」与 06「路线」的接线。

    行为（hover 描线、电流推进点亮焊盘）由 scripts/check_hero.py 在浏览器里断言。
    """

    def setUp(self):
        self.body = self.client.get(reverse("core:home")).content.decode()

    def test_three_directions_each_carry_a_component_symbol(self):
        self.assertEqual(self.body.count("nf-dir-sym"), 3)

    def test_symbols_form_the_component_to_chip_to_board_progression(self):
        """顺序本身是内容：元件 → 芯片 → 整板。换了顺序递进就没了。"""
        order = re.findall(r'nf-dir-sym.*?<svg class="icon.*?>(.*?)</svg>', self.body, re.S)
        self.assertEqual(len(order), 3)
        # 用各符号独有的几何特征认它们，比塞一堆 data 属性省事
        self.assertIn("M6 5.5v13l12-6.5Z", order[0])            # 运放的三角形
        self.assertIn('rect x="7" y="7"', order[1])             # MCU 的芯片体
        self.assertIn('rect x="3" y="5"', order[2])             # 整板的板框

    def test_roadmap_has_a_stable_anchor_and_trace_parts(self):
        self.assertIn('id="nf-roadmap"', self.body)
        self.assertIn("nf-tl-line", self.body)
        self.assertIn('id="nf-tl-progress"', self.body)
        self.assertEqual(self.body.count("nf-tl-num"), 4)


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class HomeCountdownTests(TestCase):
    """分镜 10 的招新截止倒计时。

    倒计时只在「有进行中的批次**且**设了截止时间」时才出现。没设截止时间意味着
    长期开放，倒计时无从计算 —— 那就不显示，而不是显示一个假的数字。
    """

    def setUp(self):
        from recruitment.models import Campaign

        # 迁移里预置了「2026 秋季招新」批次，它是 open 且没有截止时间的，
        # 会抢在测试批次前面被 Campaign.current() 选中。仓库里其它招新测试
        # 也是这么先停用的。
        Campaign.objects.update(is_active=False)
        cache.clear()

    def _campaign(self, **kwargs):
        from django.utils import timezone

        from recruitment.models import Campaign

        defaults = {
            "name": "2026 秋季招新",
            "is_active": True,
            "opens_at": timezone.now() - timezone.timedelta(days=1),
            "closes_at": timezone.now() + timezone.timedelta(days=10),
        }
        defaults.update(kwargs)
        return Campaign.objects.create(**defaults)

    def test_countdown_renders_with_an_open_campaign(self):
        self._campaign()
        body = self.client.get(reverse("core:home")).content.decode()
        self.assertIn("data-countdown=", body)
        self.assertIn("报名截止", body)
        # 时钟初始隐藏：渐进增强，JS 上去才放出来
        self.assertRegex(body, r'class="nf-countdown-clock"[^>]*hidden')

    def test_no_countdown_without_a_deadline(self):
        """长期开放（closes_at 为空）时不显示倒计时。"""
        self._campaign(closes_at=None)
        body = self.client.get(reverse("core:home")).content.decode()
        self.assertNotIn("data-countdown=", body)

    def test_no_countdown_when_recruitment_closed(self):
        from django.utils import timezone

        self._campaign(closes_at=timezone.now() - timezone.timedelta(days=1))
        body = self.client.get(reverse("core:home")).content.decode()
        self.assertNotIn("data-countdown=", body)

    def test_context_exposes_the_deadline_and_name_together(self):
        """导航条的「在招新」和首页的倒计时必须来自同一次判断，否则会互相打脸。"""
        self._campaign(name="测试批次")
        resp = self.client.get(reverse("core:home"))
        self.assertTrue(resp.context["recruitment_open"])
        self.assertEqual(resp.context["recruitment_name"], "测试批次")
        self.assertIsNotNone(resp.context["recruitment_closes_at"])

    def test_clock_is_hidden_from_assistive_tech(self):
        """每秒变一次的数字对读屏软件是噪音；日期那行才是信息。"""
        self._campaign()
        body = self.client.get(reverse("core:home")).content.decode()
        clock = body[body.find("nf-countdown-clock"):][:200]
        self.assertIn('aria-hidden="true"', clock)


class GuidePageTests(TestCase):
    """新生指南（`/recruit/`）的服务端接线。

    阅读体验的行为（目录通电是前缀语义、进度线跟着文档高度变、脚本挂了目录还
    是锚点）由 scripts/check_guide.py 在真实浏览器里断言。这里只守模板与 CSS
    里那几件「删了不报错、效果静默消失」的事。
    """

    def setUp(self):
        cache.clear()
        self.body = self.client.get(reverse("core:recruit")).content.decode()

    def test_chapters_and_toc_agree_on_numbering(self):
        """目录焊盘上的编号和正文标题的编号必须一一对应。

        两处各写一遍是有意的（一处在 nav、一处在 h2），但对不上就会出现
        「目录说 03、正文写 04」这种没人会去核对的错。
        """
        toc = re.findall(r'<span class="rg-pad">(\d+)</span>', self.body)
        heads = re.findall(r'<span class="rg-no">(\d+)</span>', self.body)
        self.assertEqual(toc, ["01", "02", "03", "04", "05"])
        self.assertEqual(heads, toc)

    def test_every_toc_link_points_at_a_real_section(self):
        """锚点断了不会报错，只是点了没反应。"""
        hrefs = re.findall(r'<a href="#([a-z]+)"><span class="rg-pad">', self.body)
        self.assertEqual(len(hrefs), 5)
        for anchor in hrefs:
            self.assertIn(f'<section id="{anchor}">', self.body, f"#{anchor} 没有对应的章节")

    def test_progress_bar_is_progressive_enhancement(self):
        """服务端只渲染一条 0 宽的线，宽度由脚本写。

        反过来做（服务端渲染一个假进度）会在没有 JS 时留下一条永远不动的线。
        """
        self.assertIn('id="rg-bar-fill"', self.body)
        self.assertIn('class="rg-bar"', self.body)
        self.assertIn("js/recruit-guide.js", self.body)
        # 服务端不该给出任何宽度
        bar = re.search(r'<div class="rg-bar"[^>]*>(.*?)</div>', self.body, re.S)
        self.assertIsNotNone(bar)
        self.assertNotIn("width", bar.group(1))

    def test_three_field_photo_slots_are_used(self):
        """每章一张现场照。图鉴那 69 张继续走静态 <img>，见 core/slots.py 的注释。

        数 `rg-shot` 而不是数空态：这三格会随着照片陆续到位从占位框变成真照片，
        断言的是「三章各有一格现场照」，和填没填图无关。原来写的是
        `count('class="slot is-empty rg-shot"') == 3`，给工作台那格补上照片之后
        就红了 —— 而模板一个字都没改。
        """
        for key in ("recruit.training.session", "recruit.hardware.bench",
                    "recruit.software.debug"):
            self.assertIn(f'data-slot-key="{key}"', self.body, f"模板里没有用 {key}")
        self.assertEqual(len(re.findall(r'class="slot is-\w+ rg-shot"', self.body)), 3)

    def test_reference_gallery_stays_static_images(self):
        """图鉴不该被顺手改成素材槽。

        那 69 张是元件棚拍与软件界面截图 —— 一张干净的棚拍比实验室抓拍更能说明
        问题，而素材槽的前提是「这里缺一张我们自己的照片」。真改成槽位会让驾驶舱
        的缺图清单被 69 条淹掉，真正缺的那几张反而看不见。
        """
        self.assertGreater(self.body.count("img/recruit/"), 50)

    def test_hero_keeps_the_scope_grid_usable(self):
        """`.recruit-hero` 上叠着 .nf-scope，底色只能用 background-color。

        用 `background` 简写会把 .nf-scope 的 background-image（示波器网格）
        一起重置掉 —— 网格凭空消失、不报错、截图上只是「有点暗」。这条踩过两次，
        所以直接钉在测试里。
        """
        from pathlib import Path

        from django.conf import settings

        self.assertIn("recruit-hero nf-scope", self.body)
        css = (Path(settings.BASE_DIR) / "static" / "css" / "core.css").read_text(encoding="utf-8")
        rule = re.search(r"\.recruit-hero\s*\{([^}]*)\}", css)
        self.assertIsNotNone(rule, "找不到 .recruit-hero 规则")
        body = rule.group(1)
        self.assertIn("background-color", body)
        self.assertNotRegex(
            body, r"(^|;)\s*background\s*:",
            "`.recruit-hero` 用了 background 简写，会把 .nf-scope 的网格重置掉",
        )

    def test_sections_reserve_room_for_the_fixed_nav(self):
        """没有 scroll-margin-top，点目录跳过去标题正好被固定导航盖住。"""
        from pathlib import Path

        from django.conf import settings

        css = (Path(settings.BASE_DIR) / "static" / "css" / "core.css").read_text(encoding="utf-8")
        self.assertRegex(
            css, r"\.recruit-content\s+section\s*\{[^}]*scroll-margin-top:\s*\d+px",
        )


# ---------------------------------------------------------------- 内容页共用件

def _template_text(rel: str) -> str:
    """读一个模板的原文，并摘掉 {% comment %} 块。

    注释里会写「原来是 .xx-hero，现在合并了」这种说明，纯文本扫描会把它当成
    真的还在用。素材槽的扫描测试踩过同一件事。
    """
    import re as _re
    from pathlib import Path

    from django.conf import settings

    text = (Path(settings.BASE_DIR) / "templates" / rel).read_text(encoding="utf-8")
    return _re.sub(r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", "", text, flags=_re.S)


# Tier 2 内容页里「列表页」那一档。每一页都该长同一个样子：暗场页头横幅 +
# 共用分页 + 共用空态。新加列表页时把它加进来。
LIST_TEMPLATES = [
    "news/list.html",
    "events/list.html",
    "files/list.html",
    "notify/list.html",
    "points/mine.html",
    "points/leaderboard.html",
    "projects/list.html",
    "projects/works_wall.html",
    "news/honors.html",
    "accounts/team.html",
]

# Task 18 合并掉的类名。它们在 core.css 里已经不存在了，模板里再出现就是
# 「有类名没样式」——页面照常渲染、控制台干净，只是那一块没有任何设计。
RETIRED_CLASSES = [
    "filter-tabs",   # → .pill-row > .pill
    "empty-hint",    # → .empty-state（整页）/ .inset-empty（面板里）
    "wk-hero", "hn-hero", "tm-hero",      # → .page-hero
    "wk-empty", "hn-empty", "tm-empty",   # → .empty-state
]


class ContentPageConventionTests(TestCase):
    """内容页的收敛本身要被钉住。

    Task 18 把八组页面收敛到一套共用件上。这类收敛最容易在「下一次加页面」时
    悄悄退回去 —— 复制一份旧模板、改两个字，就又多了一份 hero。所以这里扫模板
    原文，而不是只测渲染结果。
    """

    def test_every_list_page_uses_the_shared_hero(self):
        for rel in LIST_TEMPLATES:
            with self.subTest(template=rel):
                text = _template_text(rel)
                self.assertIn("page-hero", text, f"{rel} 没用共用页头横幅")
                self.assertIn("nf-scope", text, f"{rel} 的页头没叠示波器网格")

    def test_no_template_uses_a_retired_class(self):
        from pathlib import Path

        from django.conf import settings

        root = Path(settings.BASE_DIR) / "templates"
        offenders = []
        for path in root.rglob("*.html"):
            text = _template_text(str(path.relative_to(root)))
            for cls in RETIRED_CLASSES:
                if cls in text:
                    offenders.append(f"{path.relative_to(root)} → {cls}")
        self.assertFalse(offenders, "模板还在用已经删掉的类名：" + "; ".join(offenders))

    def test_frontend_templates_do_not_use_dashboard_only_classes(self):
        """`.dash-*` 只定义在 dashboard.css 里，而前台页面不加载它。

        `projects/detail.html` 真的这么写过：表格不能横向滚动、行内按钮不排成一行、
        空态是一行裸文本，而页面渲染正常、控制台干净 —— 没有任何迹象。
        """
        from pathlib import Path

        from django.conf import settings

        root = Path(settings.BASE_DIR) / "templates"
        offenders = []
        for path in root.rglob("*.html"):
            rel = str(path.relative_to(root)).replace("\\", "/")
            if rel.startswith("dashboard/"):
                continue
            text = _template_text(rel)
            if "dash-" in text:
                offenders.append(rel)
        self.assertFalse(offenders,
                         "前台模板用了只存在于 dashboard.css 的类：" + ", ".join(offenders))

    def test_list_pages_use_the_shared_pager(self):
        """分页标记原来在 11 个模板里各抄一遍，各自手拼 querystring。"""
        paged = ["news/list.html", "events/list.html", "files/list.html",
                 "notify/list.html", "points/mine.html", "projects/works_wall.html"]
        for rel in paged:
            with self.subTest(template=rel):
                text = _template_text(rel)
                self.assertIn("includes/pager.html", text, f"{rel} 没用共用分页件")
                self.assertNotIn("previous_page_number", text,
                                 f"{rel} 还在自己拼分页链接")


# 跨页转场里参与配对的模板。列表侧标 `data-vt-card` + `data-vt-part`，
# 详情侧只标 `data-vt-part`（且不在卡片里）。加新的配对就加进来。
VT_TEMPLATES = [
    "includes/work_card.html",
    "projects/works_detail.html",
    "news/list.html",
    "news/detail.html",
]

# view-transitions.js 认得、且 tokens.css 有映射的部位名。多写一个别的值不会报错，
# 只是那一处压根不参与转场。
VT_PARTS = ["cover"]


class ViewTransitionMarkupTests(TestCase):
    """跨页转场的命名元素契约。

    这一整套的失败模式全是静默的：名字重了、名字没摘、脚本晚一步挂上监听 ——
    浏览器一律「跳过转场，照常导航」，页面正常、控制台干净，只是那个「图片长大」
    的效果压根没发生。行为一侧由 scripts/check_transitions.py 在真浏览器里钉住，
    这里钉住标记与加载方式，让改模板的人当场就知道踩线了。
    """

    def _vt_css(self):
        from pathlib import Path

        from django.conf import settings

        return (Path(settings.BASE_DIR) / "static" / "css" / "tokens.css").read_text(
            encoding="utf-8")

    def test_view_transitions_script_is_not_deferred(self):
        """`pagereveal` 在新文档第一次渲染前就触发。

        defer 脚本与它的先后没有保证，慢一步监听器就没挂上 —— 转场静默退回整页
        淡入淡出，不报任何错。所以这个脚本刻意在 head 里同步加载（<2KB）。
        """
        import re

        text = _template_text("base.html")
        m = re.search(r"<script[^>]*view-transitions\.js[^>]*>", text)
        self.assertIsNotNone(m, "base.html 没有加载 view-transitions.js")
        tag = m.group(0)
        self.assertNotIn("defer", tag, "view-transitions.js 不能 defer，会错过 pagereveal")
        self.assertNotIn("async", tag, "view-transitions.js 不能 async，同上")

    def test_no_template_assigns_a_transition_name_statically(self):
        """`view-transition-name` 在一个文档里必须唯一。

        列表页十几张卡片全都命名会让浏览器直接跳过**整个**转场并报重名。所以名字
        只能由 view-transitions.js 在导航那一刻给参与的那一张，模板里一个都不许写。
        """
        from pathlib import Path

        from django.conf import settings

        root = Path(settings.BASE_DIR) / "templates"
        offenders = []
        for path in root.rglob("*.html"):
            text = _template_text(str(path.relative_to(root)))
            if "data-vt-name" in text or "view-transition-name" in text:
                offenders.append(str(path.relative_to(root)).replace("\\", "/"))
        self.assertFalse(
            offenders,
            "模板里静态指派了转场名字（必须由 view-transitions.js 在导航那刻给）："
            + ", ".join(offenders))

    def test_transition_parts_are_known_and_mapped(self):
        """标了没人认识的部位名等于没标：脚本不指派，CSS 也没有对应规则。"""
        import re

        from pathlib import Path

        from django.conf import settings

        root = Path(settings.BASE_DIR) / "templates"
        css = self._vt_css()
        js = (Path(settings.BASE_DIR) / "static" / "js" / "view-transitions.js").read_text(
            encoding="utf-8")
        seen = set()
        for path in root.rglob("*.html"):
            text = _template_text(str(path.relative_to(root)))
            seen.update(re.findall(r'data-vt-part="([^"]+)"', text))
        self.assertTrue(seen, "一个 data-vt-part 都没有，跨页转场的配对标记丢了")
        self.assertEqual(seen - set(VT_PARTS), set(),
                         f"模板用了未登记的部位名，脚本不会指派它：{seen - set(VT_PARTS)}")
        for part in sorted(seen):
            with self.subTest(part=part):
                self.assertIn(f'"{part}"', js, f"view-transitions.js 的 PARTS 里没有 {part}")
                self.assertIn(f'[data-vt-name="{part}"]', css,
                              f"tokens.css 没有把 {part} 映射成 view-transition-name")

    def test_cards_and_parts_come_in_pairs(self):
        """光标 `data-vt-card` 没有内部部位，或反过来，两边都配不上对。"""
        for rel in VT_TEMPLATES:
            with self.subTest(template=rel):
                text = _template_text(rel)
                self.assertIn("data-vt-part", text, f"{rel} 少了配对部位标记")
        for rel in ["includes/work_card.html", "news/list.html"]:
            with self.subTest(template=rel):
                self.assertIn("data-vt-card", _template_text(rel),
                              f"{rel} 是列表侧，必须标 data-vt-card")

    def test_paired_cover_keeps_its_crossfade(self):
        """配上对的 old/new 靠 `mix-blend-mode: plus-lighter` 交叉淡入。

        在这一对上写 `animation: none` 或把 blend 改成 normal，既丢了过渡、也让
        `document.getAnimations()` 再也看不到这两个伪元素 —— 而 check_transitions.py
        正是靠它判断有没有配上对。真踩过一次，表现是「有动画但没配对」。
        """
        import re

        css = self._vt_css()
        m = re.search(
            r"::view-transition-old\(vt-cover\)\s*,\s*"
            r"::view-transition-new\(vt-cover\)\s*\{(.*?)\}", css, re.S)
        self.assertIsNotNone(m, "tokens.css 里找不到 vt-cover 的 old/new 规则块")
        body = m.group(1)
        self.assertNotIn("animation", body, "别在 vt-cover 的 old/new 上关动画")
        self.assertNotIn("mix-blend-mode", body,
                         "别覆盖 vt-cover 的 mix-blend-mode，plus-lighter 是不透风的关键")

    def test_reduced_motion_stops_the_static_names(self):
        """减动效下 JS 压根不指派名字，只剩两个静态名 —— 也要停住才是干净瞬切。

        写法上刻意不用「split 到 reduced-motion 之后再找」：`page-hero` 的组规则在
        外面也有一条，那样写在 media 块整个消失时照样通过。这里改成拿每个名字最后
        一次出现的位置，跟 media 查询的位置比。
        """
        css = self._vt_css()
        guard = css.find("prefers-reduced-motion")
        self.assertNotEqual(guard, -1, "tokens.css 里没有 prefers-reduced-motion 分支")
        for name in ("root", "site-nav", "page-hero"):
            with self.subTest(name=name):
                sel = (f"::view-transition-old({name})" if name == "root"
                       else f"::view-transition-group({name})")
                self.assertGreater(
                    css.rfind(sel), guard,
                    f"减动效分支里没有 {name} 的关停规则（外面那条不算）")
                stopped = css[css.rfind(sel):]
                self.assertRegex(stopped[:400], r"animation:\s*none",
                                 f"{name} 在减动效分支里没被停住")


# Task 20 退役的取值。它们**渲染起来完全正常**，只是对比度不够 —— 再出现就是
# 悄悄把一处文字推回 AA 门槛以下。
RETIRED_COLORS = [
    ("#6b7280", "页脚版权条的灰，在纯黑上只有 4.21:1 → 用 var(--muted-dim)"),
]


class AccessibilityContractTests(TestCase):
    """无障碍里「一眼看不出坏了」的那几条。

    行为一侧由 scripts/check_a11y.py 在真浏览器里量（焦点顺序、提示可见性、
    对比度现算）。这里钉住的是标记与令牌的契约 —— 那些一改就静默失效的地方。
    """

    def _css(self, name):
        from pathlib import Path

        from django.conf import settings

        return (Path(settings.BASE_DIR) / "static" / "css" / name).read_text(encoding="utf-8")

    def test_no_template_has_a_multiline_hash_comment(self):
        """**Django 的 `{# #}` 只支持单行。**

        跨行写的话它不是注释，而是**会被原样渲染出来的正文** —— 而且模板照常编译、
        测试照常通过、控制台干净。真踩过：`base.html` 里一段解释页脚标题层级的
        跨行 `{# #}`，把「页脚各栏用 h2：……」整段印在了线上每一页的页脚上方。
        跨行注释一律用 `{% comment %}`。
        """
        import re

        from pathlib import Path

        from django.conf import settings

        root = Path(settings.BASE_DIR) / "templates"
        offenders = []
        for path in root.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            for m in re.finditer(r"\{#", text):
                tail = text[m.start():]
                end = tail.find("#}")
                body = tail if end == -1 else tail[:end]
                if "\n" in body:
                    rel = str(path.relative_to(root)).replace("\\", "/")
                    line = text[:m.start()].count("\n") + 1
                    why = "没有闭合" if end == -1 else "跨行"
                    offenders.append(f"{rel}:{line}（{why}）")
        self.assertFalse(
            offenders,
            "这些 {# #} 会被当正文渲染出来，改用 {% comment %}：" + "; ".join(offenders))

    def test_skip_link_is_the_first_focusable_thing(self):
        """跳转链接必须是 <body> 里第一个可聚焦元素，否则它没有意义。

        固定导航里有十几个可聚焦项；这条链接晚一步出现，键盘用户就还是得先
        穿过整排导航 —— 而页面看起来完全正常。
        """
        import re

        text = _template_text("base.html")
        body = text.split("<body", 1)[1]
        self.assertIn('class="skip-link sr-only"', body, "base.html 没有跳转链接")
        # 第一个 href / 第一个 button 都不能出现在它前面
        first_focusable = re.search(r"<(a|button)\b", body)
        self.assertIsNotNone(first_focusable)
        self.assertEqual(
            first_focusable.group(1), "a",
            "<body> 里第一个可聚焦元素不是跳转链接")
        self.assertLess(
            body.index("skip-link"), body.index("<header"),
            "跳转链接要排在 <header> 之前")

    def test_main_is_the_skip_target(self):
        """`#main` 要有 `tabindex="-1"`：只有 id 时部分浏览器只滚动、不移动焦点，
        于是「跳到主要内容」之后再按 Tab 又回到了导航里。"""
        text = _template_text("base.html")
        self.assertRegex(
            text, r'<main[^>]*id="main"[^>]*tabindex="-1"',
            '<main> 缺 id="main" 或 tabindex="-1"')
        self.assertIn('href="#main"', text, "跳转链接的 href 和 <main> 的 id 对不上")

    def test_messages_render_inside_main(self):
        """**消息提示必须在 `<main>` 里。**

        在 `<main>` 外面时它拿不到 `.site-main` 那份 `padding-top: 74px`，于是整条
        被高 74px 的固定导航盖住 —— 「保存成功」「验证码已发送」一个都看不见，
        而文字在 DOM 里，按 textContent 断言的检查脚本全都通过。
        """
        text = _template_text("base.html")
        main_at = text.index("<main")
        end_at = text.index("</main>")
        msg_at = text.index("{% if messages %}")
        self.assertTrue(
            main_at < msg_at < end_at,
            "消息提示不在 <main> 里 —— 它会被固定导航整条盖住")
        self.assertRegex(text, r'class="container messages-wrap" role="status"',
                         "消息提示区少了 role=status")

    def test_sr_only_stays_readable_by_screen_readers(self):
        """`.sr-only` 不能用 display:none / visibility:hidden —— 那两种写法读屏
        软件也读不到，等于这段文字压根没写。"""
        css = self._css("tokens.css")
        block = css.split(".sr-only {", 1)[1].split("}", 1)[0]
        self.assertNotIn("display: none", block)
        self.assertNotIn("visibility: hidden", block)
        self.assertIn("clip-path", block, ".sr-only 应当靠 clip-path 藏起来")
        self.assertIn(".skip-link:focus", css, "跳转链接聚焦时没有显形的规则")

    def test_light_sections_use_the_darkened_accent(self):
        """白区上的强调色必须是压暗过的那一支。

        `--accent` (#0da9cd) 放在 `--paper` 上只有 2.61:1 —— 连大字要的 3:1 都不到。
        白区里用它的正好是 eyebrow 小字与大标题里的强调词两处。
        """
        tokens = self._css("tokens.css")
        core = self._css("core.css")
        self.assertIn("--accent-ink:", tokens, "缺 --accent-ink 令牌")
        for sel in (".nf-light .nf-eyebrow", ".nf-light .nf-display .accent"):
            with self.subTest(selector=sel):
                block = core.split(sel + " {", 1)
                self.assertEqual(len(block), 2, f"{sel} 这条规则不见了")
                self.assertIn("var(--accent-ink)", block[1].split("}", 1)[0],
                              f"{sel} 没用压暗过的强调色")

    def test_no_stylesheet_reuses_a_retired_color(self):
        from pathlib import Path

        from django.conf import settings

        root = Path(settings.BASE_DIR) / "static" / "css"
        offenders = []
        for path in sorted(root.glob("*.css")):
            text = path.read_text(encoding="utf-8")
            for value, why in RETIRED_COLORS:
                # 令牌定义那一行的注释里会提到旧值，按「后面跟着分号」筛掉注释
                if f"{value};" in text or f"{value} " in text.replace(f"{value} 字面值", ""):
                    offenders.append(f"{path.name} → {value}（{why}）")
        self.assertFalse(offenders, "样式表又用回了退役取值：" + "; ".join(offenders))

    def test_current_filter_pill_is_not_signalled_by_colour_alone(self):
        """`.pill.is-current` 改的只有三个颜色，所以必须同时给 `aria-current`。

        全站 14 处药丸行，条件写两遍迟早只改一处 —— 所以模板里用
        `{% if %}class="pill is-current" aria-current="page"{% else %}` 的写法，
        一个条件同时给出两样东西。这里扫的就是「有 is-current 就必须有 aria-current」。
        """
        import re

        from pathlib import Path

        from django.conf import settings

        root = Path(settings.BASE_DIR) / "templates"
        offenders = []
        seen = 0
        for path in root.rglob("*.html"):
            text = _template_text(str(path.relative_to(root)))
            for m in re.finditer(r'class="pill is-current"([^>]*)', text):
                seen += 1
                if 'aria-current="page"' not in m.group(1):
                    offenders.append(str(path.relative_to(root)).replace("\\", "/"))
        self.assertGreaterEqual(seen, 10,
                                "扫到的药丸太少，这条断言可能在空跑")
        self.assertFalse(offenders,
                         "药丸的当前态只靠颜色、没给 aria-current：" + ", ".join(offenders))


class DeployPerfContractTests(TestCase):
    """部署侧那几条「不生效也不报错」的性能配置。

    改完要 `ops/deploy.sh` 才会到生产上（它自己会跑 `nginx -t`）。
    """

    def _nginx(self):
        from pathlib import Path

        from django.conf import settings

        return (Path(settings.BASE_DIR).parent / "ops" / "nginx"
                / "heuesta.cn.conf").read_text(encoding="utf-8")

    def test_gzip_covers_both_spellings_of_the_javascript_mime(self):
        """`.js` 的默认 MIME 在 nginx 1.21.1 从 application/javascript 改成了
        text/javascript。只列前者的话，**新版 nginx 上所有 JS 都不压缩发** ——
        three 365KB、gsap 73KB 原样过网，而页面照常能用、日志里什么都没有。"""
        conf = self._nginx()
        types = conf.split("gzip_types", 1)[1].split(";", 1)[0]
        for mime in ("text/javascript", "application/javascript"):
            with self.subTest(mime=mime):
                self.assertIn(mime, types, f"gzip_types 少了 {mime}")
        self.assertIn("gzip_vary on", conf,
                      "前面挂着 CDN，必须发 Vary: Accept-Encoding")

    def test_static_sends_exactly_one_cache_control(self):
        """`expires 365d` 自己会发一条 max-age，再 `add_header Cache-Control`
        就成了两条 —— 各家 CDN 取哪条不好说。只留 add_header 那一条。"""
        block = self._nginx().split("location /static/", 1)[1].split("}", 1)[0]
        # 先摘掉注释行：这一块的注释里正好解释了「为什么不用 expires」，
        # 纯文本扫描会把说明当成配置。素材槽与内容页的扫描测试踩过同一个形状。
        block = "\n".join(ln for ln in block.splitlines()
                          if not ln.strip().startswith("#"))
        self.assertNotIn("expires", block,
                         "/static/ 同时用了 expires 与 add_header，会发两条 Cache-Control")
        self.assertIn("immutable", block, "/static/ 少了 immutable")
        self.assertIn("max-age=31536000", block, "/static/ 的 max-age 不见了")

    def test_only_shared_body_fonts_are_preloaded(self):
        import re

        text = _template_text("base.html")
        preloads = re.findall(r'<link rel="preload"[^>]*as="font"[^>]*>', text)
        self.assertEqual(len(preloads), 2)
        for weight in ("Regular", "Bold"):
            self.assertIn(f"SourceHanSansCN-{weight}-subset.woff2", " ".join(preloads))

    def test_auth_styles_are_not_loaded_on_public_content_pages(self):
        self.assertNotContains(self.client.get("/help/"), "css/auth.css")
        self.assertContains(self.client.get("/accounts/register/"), "css/auth.css")

    def test_body_font_family_is_self_hosted_not_the_system_stack(self):
        """正文是站上读得最多的文字，不能交给访客的操作系统决定。

        原来 `body` 直接写系统字体栈 —— Mac 上是苹方、Windows 上是微软雅黑，
        两个访客看到的是两种气质的网站，而且都不是我们定的那个。
        这条同时钉住「系统栈只能当兜底」：它必须还在，但排在自托管家族后面。
        """
        from pathlib import Path

        from django.conf import settings

        css = (Path(settings.BASE_DIR) / "static" / "css" / "tokens.css").read_text(
            encoding="utf-8")
        self.assertIn("--font-body: \"ESTA Sans\"", css)
        self.assertRegex(css, r"body\s*\{[^}]*font-family:\s*var\(--font-body\)")
        # 兜底栈还在，且 ESTA Sans 排在它前面
        self.assertIn("--font-sys: -apple-system", css)
        self.assertLess(css.index('--font-body: "ESTA Sans"'), css.index("body {"))
        for weight, path in (("400", "SourceHanSansCN-Regular-subset.woff2"),
                             ("700", "SourceHanSansCN-Bold-subset.woff2")):
            with self.subTest(weight=weight):
                block = css[css.index(path):]
                self.assertIn(f"font-weight: {weight};", block[:200],
                              f"{path} 的 @font-face 没声明 {weight} 字重")

    def test_clickjacking_header_comes_from_nginx_because_simpleui_drops_it(self):
        """**django-simpleui 会把 XFrameOptionsMiddleware 从 MIDDLEWARE 里 pop 掉。**

        它的 `apps.py` 在 `ready()` 里无条件删（后台 UI 靠 iframe 开标签页）。于是
        `settings/base.py` 里那一行看着好好的，运行时却不在 —— **整站不发
        X-Frame-Options**，登录页、注册表单、驾驶舱都能被任意站点套进 iframe。

        这条测试同时钉住两件事：
          1. 现状确实如此（哪天 simpleui 不再摘它，这里会红，那时就能把 nginx
             那行去掉、把保护交回 Django）；
          2. nginx 侧真的把这个头补上了。
        """
        from django.conf import settings

        self.assertIn(
            "django.middleware.clickjacking.XFrameOptionsMiddleware",
            self._settings_source(),
            "base.py 里那一行别删 —— simpleui 不再摘它时保护要能自动回来")
        self.assertNotIn(
            "django.middleware.clickjacking.XFrameOptionsMiddleware",
            settings.MIDDLEWARE,
            "simpleui 似乎不再摘这个中间件了 —— 那就可以把 nginx 里那条 "
            "add_header X-Frame-Options 去掉，改回依赖 Django")
        self.assertEqual(settings.X_FRAME_OPTIONS, "SAMEORIGIN",
                         "simpleui 后台要同源 iframe，不能是 DENY")

        block = self._nginx().split("location / {", 1)[1].split("\n    }", 1)[0]
        self.assertRegex(
            block, r'add_header\s+X-Frame-Options\s+"SAMEORIGIN"\s+always',
            "nginx 的 location / 里没有补 X-Frame-Options（带 always）")

    def _settings_source(self):
        from pathlib import Path

        from django.conf import settings

        return (Path(settings.BASE_DIR) / "config" / "settings" / "base.py").read_text(
            encoding="utf-8")

    def test_only_view_transitions_blocks_parsing(self):
        """head 里除了 view-transitions.js 不该再有同步脚本（它刻意不 defer，
        `pagereveal` 等不起）。新加脚本忘了 defer 是最常见的一次性退步。"""
        import re

        text = _template_text("base.html")
        head = text.split("</head>", 1)[0]
        blocking = [
            m.group(0) for m in re.finditer(r"<script(?![^>]*\btype=)[^>]*\bsrc=[^>]*>", head)
            if "defer" not in m.group(0) and "async" not in m.group(0)
        ]
        self.assertEqual(len(blocking), 1, f"head 里的阻塞脚本不止一个：{blocking}")
        self.assertIn("view-transitions.js", blocking[0])


class PagerIncludeTests(TestCase):
    """共用分页件：只有一页时整块不渲染，多页时带无障碍语义并保留筛选参数。"""

    def _render(self, total, page_number, query=""):
        from django.core.paginator import Paginator
        from django.template.loader import render_to_string
        from django.test import RequestFactory

        # 必须走 render_to_string(..., request=)：`{% querystring %}` 直接读
        # `context.request`，光把 request 塞进普通 Context 里它拿不到
        # （AttributeError: 'Context' object has no attribute 'request'）。
        # 带 request 渲染会跑全套 context processor，所以要自己补上 `user`——
        # RequestFactory 造的请求没过 AuthenticationMiddleware。
        from django.contrib.auth.models import AnonymousUser

        request = RequestFactory().get("/news/" + query)
        request.user = AnonymousUser()
        page = Paginator(list(range(total)), 10).page(page_number)
        return render_to_string("includes/pager.html", {"page": page}, request=request)

    def test_single_page_renders_nothing(self):
        """调用方不用自己包 {% if %}，所以这条要保证。"""
        self.assertEqual(self._render(5, 1).strip(), "")

    def test_multi_page_has_nav_semantics(self):
        html = self._render(25, 2)
        self.assertIn('<nav class="pagination" aria-label="分页">', html)
        self.assertIn('aria-current="page"', html)
        self.assertIn('rel="prev"', html)
        self.assertIn('rel="next"', html)

    def test_existing_filters_survive_paging(self):
        """**本任务的核心回归。** 原来每个模板自己拼 `?page=N&category=...`，
        抄漏一个参数就是「翻到第二页筛选没了」，而页面照常渲染、没有报错。
        """
        html = self._render(25, 2, "?category=notice&q=%E7%94%B5%E8%B5%9B")
        self.assertIn("category=notice", html)
        self.assertIn("q=%E7%94%B5%E8%B5%9B", html)
        self.assertIn("page=3", html)
        self.assertIn("page=1", html)

    def test_first_and_last_page_keep_the_arrow_slot(self):
        """首页/末页那一侧仍占位，否则「下一页」会从右边跳到左边。"""
        first = self._render(25, 1)
        self.assertIn('class="is-disabled"', first)
        self.assertNotIn('rel="prev"', first)
        last = self._render(25, 3)
        self.assertIn('class="is-disabled"', last)
        self.assertNotIn('rel="next"', last)


class NavigationTests(TestCase):
    """主导航：条目数量是硬约束，三个墙必须能到达。"""

    def test_three_walls_are_reachable_from_the_nav(self):
        """Task 15 / 16 / 17 都把导航入口推迟到了 Task 18。"""
        body = self.client.get(reverse("core:home")).content.decode()
        nav = body.split('id="nav-links"', 1)[1].split("</nav>", 1)[0]
        for url in (reverse("works:wall"), reverse("honors:wall"), reverse("team:wall")):
            self.assertIn(f'href="{url}"', nav, f"导航里没有 {url}")

    def test_top_level_item_count_stays_small(self):
        """顶层平铺 10 条时实测只剩 10px 余量，用户名长一点就挤到换行。
        条目要往折叠组里放，不要往顶层加。
        """
        import re as _re

        body = self.client.get(reverse("core:home")).content.decode()
        nav = body.split('id="nav-links"', 1)[1].split("</nav>", 1)[0]
        groups = nav.count("<details")
        # 先把折叠组整段挖掉，否则菜单里的二级链接会被算成顶层条目
        # （实测数出 12 个链接 —— 那正是收敛之前的规模，断言等于没写）
        top_only = _re.sub(r"<details.*?</details>", "", nav, flags=_re.S)
        top_links = _re.findall(r"<a\s", top_only)
        self.assertLessEqual(len(top_links) + groups, 6,
                             f"顶层条目太多：{len(top_links)} 个链接 + {groups} 个折叠组")

    def test_nav_groups_are_native_details(self):
        """折叠用原生 <details>：没有 JS 也能展开、键盘可达、读屏认得。
        改成「按钮 + JS 加类」的话，脚本挂了整组链接就不可达。
        """
        body = self.client.get(reverse("core:home")).content.decode()
        nav = body.split('id="nav-links"', 1)[1].split("</nav>", 1)[0]
        self.assertEqual(nav.count('<details class="nav-group" data-nav-group>'), 2)
        self.assertEqual(nav.count("<summary>"), 2)
