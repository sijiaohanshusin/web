import re
import tempfile

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from accounts import roles
from accounts.models import Position, ReturningMembershipRequest
from core import slots as slot_registry
from core.models import CarouselImage, MediaSlot
# 生成真图的辅助函数放在 core.tests 里，测试模块之间互相 import 是正常的。
# 别再手写 base64 常量：ImageField 表单校验走 Pillow 的 verify()，比 open() 严格。
from core.tests import make_mp4, make_png

User = get_user_model()


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.applicant = User.objects.create_user(username="applicant", password="x")
        self.applicant.set_level(roles.LEVEL_APPLICANT)
        self.officer = User.objects.create_user(username="officer", password="x")
        self.officer.set_level(roles.LEVEL_OFFICER)
        self.admin = User.objects.create_user(username="admin1", password="x")
        self.admin.set_level(roles.LEVEL_ADMIN)

    def test_anonymous_redirected(self):
        resp = self.client.get(reverse("dashboard:overview"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_applicant_forbidden(self):
        self.client.login(username="applicant", password="x")
        self.assertEqual(self.client.get(reverse("dashboard:overview")).status_code, 403)

    def test_officer_can_view(self):
        self.client.login(username="officer", password="x")
        self.assertEqual(self.client.get(reverse("dashboard:overview")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:members")).status_code, 200)

    def test_officer_forbidden_from_medals(self):
        self.client.login(username="officer", password="x")
        self.assertEqual(self.client.get(reverse("dashboard:medals")).status_code, 403)

    def test_admin_can_view_medals_positions_site(self):
        self.client.login(username="admin1", password="x")
        self.assertEqual(self.client.get(reverse("dashboard:medals")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:positions")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:site_settings")).status_code, 200)

    def test_chair_position_grants_dashboard_without_staff_level(self):
        chair = User.objects.create_user(username="chair", password="x")
        chair.set_level(roles.LEVEL_FORMAL)
        chair.position = Position.objects.get(name="主席")
        chair.save(update_fields=["position"])
        self.client.login(username="chair", password="x")
        self.assertEqual(self.client.get(reverse("dashboard:overview")).status_code, 200)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class MemberActionTests(TestCase):
    def setUp(self):
        self.officer = User.objects.create_user(username="officer", password="x")
        self.officer.set_level(roles.LEVEL_OFFICER)
        self.admin = User.objects.create_user(username="admin1", password="x")
        self.admin.set_level(roles.LEVEL_ADMIN)
        self.pending = User.objects.create_user(username="newbie", password="x", is_active=False)

    def test_officer_can_promote_recruit_to_preparatory(self):
        self.client.login(username="officer", password="x")
        self.client.post(reverse("dashboard:member_action"), {"action": "promote_prep", "ids": [self.pending.pk]})
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.member_level, roles.LEVEL_PREPARATORY)
        self.assertTrue(self.pending.is_active)

    def test_officer_can_promote_formal(self):
        self.client.login(username="officer", password="x")
        self.client.post(reverse("dashboard:member_action"), {"action": "promote_formal", "ids": [self.pending.pk]})
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.member_level, roles.LEVEL_FORMAL)

    def test_officer_cannot_make_admin(self):
        self.client.login(username="officer", password="x")
        self.client.post(reverse("dashboard:member_action"), {"action": "make_admin", "ids": [self.pending.pk]})
        self.pending.refresh_from_db()
        self.assertNotEqual(self.pending.member_level, roles.LEVEL_ADMIN)

    def test_promote_cannot_demote_administrators_or_existing_members(self):
        formal = User.objects.create_user(username="existing-formal", member_level=roles.LEVEL_FORMAL)
        self.client.force_login(self.officer)
        response = self.client.post(reverse("dashboard:member_action"), {
            "action": "promote_prep", "ids": [self.admin.pk, formal.pk, self.pending.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.admin.refresh_from_db()
        formal.refresh_from_db()
        self.pending.refresh_from_db()
        self.assertEqual(self.admin.member_level, roles.LEVEL_ADMIN)
        self.assertTrue(self.admin.is_staff)
        self.assertEqual(formal.member_level, roles.LEVEL_FORMAL)
        self.assertEqual(self.pending.member_level, roles.LEVEL_PREPARATORY)

    def test_officer_cannot_change_independently_granted_staff_account(self):
        legacy = User.objects.create_user(username="legacy-staff", member_level=1, is_staff=True)
        self.client.force_login(self.officer)
        self.client.post(reverse("dashboard:member_action"), {"action": "promote_formal", "ids": [legacy.pk]})
        legacy.refresh_from_db()
        self.assertTrue(legacy.is_staff)
        self.assertEqual(legacy.member_level, 1)

    def test_member_action_rejects_malformed_identifiers_without_500(self):
        self.client.force_login(self.officer)
        response = self.client.post(reverse("dashboard:member_action"), {"action": "promote_formal", "ids": ["not-an-id"]})
        self.assertEqual(response.status_code, 302)

    def test_member_action_cannot_redirect_off_site(self):
        self.client.force_login(self.officer)
        response = self.client.post(reverse("dashboard:member_action"), {"action": "promote_formal", "next": "https://example.com/", "ids": []})
        self.assertEqual(response.url, reverse("dashboard:members"))

    def test_admin_can_make_officer(self):
        self.client.login(username="admin1", password="x")
        self.client.post(reverse("dashboard:member_action"), {"action": "make_officer", "ids": [self.pending.pk]})
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.member_level, roles.LEVEL_OFFICER)

    def test_returning_rejection_preserves_record(self):
        request = ReturningMembershipRequest.objects.create(
            user=self.pending,
            requested_role=ReturningMembershipRequest.RequestedRole.MEMBER,
        )
        self.client.login(username="admin1", password="x")
        self.client.post(reverse("dashboard:returning_review", args=[request.pk]), {
            "decision": "reject", "note": "资料待核实",
        })
        self.assertTrue(User.objects.filter(pk=self.pending.pk).exists())
        request.refresh_from_db()
        self.assertEqual(request.status, ReturningMembershipRequest.Status.REJECTED)
        self.assertEqual(request.review_note, "资料待核实")

    def test_returning_chair_approval_activates_and_assigns_position(self):
        request = ReturningMembershipRequest.objects.create(
            user=self.pending,
            requested_role=ReturningMembershipRequest.RequestedRole.MEMBER,
        )
        self.client.login(username="admin1", password="x")
        self.client.post(reverse("dashboard:returning_review", args=[request.pk]), {
            "decision": "approve",
            "role": ReturningMembershipRequest.RequestedRole.HARDWARE_CHAIR,
        })
        self.pending.refresh_from_db()
        request.refresh_from_db()
        self.assertTrue(self.pending.is_active)
        self.assertEqual(self.pending.member_level, roles.LEVEL_FORMAL)
        self.assertEqual(self.pending.position.name, "硬件主席")
        self.assertTrue(self.pending.position.grants_management)
        self.assertEqual(request.status, ReturningMembershipRequest.Status.APPROVED)


def _png(name="p.png"):
    return make_png(name, size=(1, 1))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="esta-test-media-"))
class MediaSlotDashboardTests(TestCase):
    """素材中心。

    这一页的价值全在「能列出还没上传的槽位」——所以最重要的断言不是「上传成功」，
    而是「登记表里的每一个槽位都出现在页面上，哪怕它在数据库里没有任何记录」。
    """

    def setUp(self):
        cache.clear()
        self.url = reverse("dashboard:media_slots")
        self.officer = User.objects.create_user(username="officer", password="x")
        self.officer.set_level(roles.LEVEL_OFFICER)
        self.applicant = User.objects.create_user(username="applicant", password="x")
        self.applicant.set_level(roles.LEVEL_APPLICANT)

    def login(self):
        self.client.login(username="officer", password="x")

    # ---------------- 权限 ----------------

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp.url)

    def test_non_officer_forbidden(self):
        self.client.login(username="applicant", password="x")
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_officer_allowed_without_staff_flag(self):
        """站务不是 is_staff（那是管理员级），素材中心必须对站务开放 ——
        真正拍照的人是他们，不能只让管理员能上传。"""
        self.login()
        self.assertFalse(self.officer.is_staff)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    # ---------------- 清单 ----------------

    def test_lists_every_registered_slot_even_with_no_db_row(self):
        self.login()
        body = self.client.get(self.url).content.decode()
        self.assertEqual(MediaSlot.objects.count(), 0)
        for spec in slot_registry.SLOTS:
            self.assertIn(spec.key, body, f"素材中心没有列出 {spec.key}")
            self.assertIn(spec.label, body)

    def test_shows_the_shooting_brief_so_people_know_what_to_shoot(self):
        self.login()
        body = self.client.get(self.url).content.decode()
        for spec in slot_registry.SLOTS:
            self.assertIn(escape(spec.brief), body, f"{spec.key} 的拍摄要求没显示")

    def test_todo_list_puts_empty_slots_before_fallback_ones(self):
        self.login()
        ctx = self.client.get(self.url).context
        states = [c["state"] for c in ctx["todo"]]
        self.assertIn("missing", states)
        # 一旦出现 fallback，后面不能再有 missing
        first_fallback = states.index("fallback") if "fallback" in states else len(states)
        self.assertNotIn("missing", states[first_fallback:])

    def test_counts_treat_fallback_slots_as_not_missing(self):
        """有兜底图的位置在官网上是有图的，不该算进「还空着」。"""
        self.login()
        ctx = self.client.get(self.url).context
        with_fallback = sum(1 for s in slot_registry.SLOTS if s.fallback)
        self.assertEqual(ctx["missing"], len(slot_registry.SLOTS) - with_fallback)

    def test_sidebar_badge_counts_missing_slots(self):
        self.login()
        self.assertEqual(
            self.client.get(self.url).context["media_missing"],
            sum(1 for s in slot_registry.SLOTS if not s.fallback),
        )

    # ---------------- 写操作 ----------------

    def test_upload_creates_slot_with_key_and_author(self):
        self.login()
        key = "home.gallery.group"
        prefix = key.replace(".", "_")
        resp = self.client.post(self.url, {
            "action": "save", "key": key,
            f"{prefix}-image": _png(),
            f"{prefix}-alt": "2025 级全员合照",
            f"{prefix}-caption": "实验室门口",
            f"{prefix}-credit": "小李",
            f"{prefix}-focal_x": 40, f"{prefix}-focal_y": 30,
            f"{prefix}-is_active": "on",
        })
        self.assertEqual(resp.status_code, 302)
        obj = MediaSlot.objects.get(key=key)
        self.assertEqual(obj.alt, "2025 级全员合照")
        self.assertEqual(obj.updated_by, self.officer)
        self.assertEqual((obj.focal_x, obj.focal_y), (40, 30))
        # 真实像素尺寸要被记下来，模板靠它写 width/height
        self.assertEqual((obj.width, obj.height), (1, 1))

    def test_uploaded_image_shows_up_on_the_public_home_page(self):
        """端到端：上传完，官网那一格就该从占位框变成照片。"""
        self.login()
        key = "home.gallery.group"
        prefix = key.replace(".", "_")
        self.client.post(self.url, {
            "action": "save", "key": key,
            f"{prefix}-image": _png(), f"{prefix}-alt": "合照来了",
            f"{prefix}-focal_x": 50, f"{prefix}-focal_y": 50, f"{prefix}-is_active": "on",
        })
        self.client.logout()
        body = self.client.get(reverse("core:home")).content.decode()
        self.assertIn("合照来了", body)

    def test_unknown_key_is_rejected_and_creates_nothing(self):
        self.login()
        resp = self.client.post(self.url, {
            "action": "save", "key": "home.nope.typo", "nope-image": _png(),
        }, follow=True)
        self.assertEqual(MediaSlot.objects.count(), 0)
        self.assertContains(resp, "没有登记过的素材槽")

    def test_saving_without_a_new_file_keeps_the_existing_image(self):
        """只想改图注时不该被迫重新上传。"""
        self.login()
        key = "home.gallery.lab"
        prefix = key.replace(".", "_")
        obj = MediaSlot.objects.create(key=key, image=_png("keep.png"), alt="旧")
        original = obj.image.name

        self.client.post(self.url, {
            "action": "save", "key": key,
            f"{prefix}-alt": "新描述", f"{prefix}-caption": "改了图注",
            f"{prefix}-focal_x": 50, f"{prefix}-focal_y": 50, f"{prefix}-is_active": "on",
        })
        obj.refresh_from_db()
        self.assertEqual(obj.alt, "新描述")
        self.assertEqual(obj.image.name, original)

    def test_focal_out_of_range_is_rejected(self):
        self.login()
        key = "home.gallery.lab"
        prefix = key.replace(".", "_")
        MediaSlot.objects.create(key=key, image=_png("f.png"), focal_x=50)
        resp = self.client.post(self.url, {
            "action": "save", "key": key,
            f"{prefix}-focal_x": 140, f"{prefix}-focal_y": 50, f"{prefix}-is_active": "on",
        }, follow=True)
        self.assertContains(resp, "保存失败")
        self.assertEqual(MediaSlot.objects.get(key=key).focal_x, 50)

    def test_toggle_returns_the_slot_to_placeholder(self):
        self.login()
        key = "home.gallery.award"
        MediaSlot.objects.create(key=key, image=_png("t.png"))
        self.client.post(self.url, {"action": "toggle", "key": key})
        self.assertFalse(MediaSlot.objects.get(key=key).is_active)

    def test_delete_removes_the_row(self):
        self.login()
        key = "home.gallery.award"
        MediaSlot.objects.create(key=key, image=_png("d.png"))
        self.client.post(self.url, {"action": "delete", "key": key})
        self.assertFalse(MediaSlot.objects.filter(key=key).exists())

    # ---------------- 旧轮播图搬迁 ----------------

    def test_migrating_a_carousel_image_copies_it_into_a_slot(self):
        self.login()
        legacy = CarouselImage.objects.create(
            title="老合照", caption="2024 年拍的", image=_png("legacy.png"),
        )
        key = "home.gallery.group"
        self.client.post(self.url, {
            "action": "migrate", "key": key, "carousel_id": legacy.pk,
        })
        obj = MediaSlot.objects.get(key=key)
        self.assertTrue(obj.is_active)
        self.assertEqual(obj.alt, "老合照")
        self.assertEqual(obj.caption, "2024 年拍的")
        # 复制而非移动：原记录留着，搬错了还能重来
        self.assertTrue(CarouselImage.objects.filter(pk=legacy.pk).exists())
        self.assertNotEqual(obj.image.name, legacy.image.name)

    def test_migrating_to_an_unknown_key_fails_loudly(self):
        self.login()
        legacy = CarouselImage.objects.create(title="x", image=_png("l2.png"))
        resp = self.client.post(self.url, {
            "action": "migrate", "key": "not.a.slot", "carousel_id": legacy.pk,
        }, follow=True)
        self.assertContains(resp, "搬迁失败")
        self.assertEqual(MediaSlot.objects.count(), 0)

    # ---------------- 深链 ----------------

    def test_key_query_param_is_passed_through_for_highlighting(self):
        """官网占位框的「上传这张 →」带着 ?key= 过来，页面要能定位到那张卡片。"""
        self.login()
        resp = self.client.get(self.url, {"key": "home.gallery.lab"})
        self.assertEqual(resp.context["focus_key"], "home.gallery.lab")
        self.assertContains(resp, 'data-slot-card="home.gallery.lab"')

    def test_public_placeholder_links_to_the_media_center(self):
        """这条守住 URL 名字：{% slot %} 靠 reverse('dashboard:media_slots')
        决定要不要显示上传入口，改名会让入口静默消失。

        取样页面从首页换到了新生指南：首页六格走廊现在全有素材，剩下的那个
        影像区槽位是 `show_cta=False`（旁边就是播放按钮，再来一个上传链接是噪音），
        于是首页一个上传入口都不剩。写死 `?key=home.gallery.group` 的老写法就是
        这么被「照片补齐了」弄红的。

        断言改成对**页面上还缺素材的每一格**都要求带着直达链接，并先确认真的
        有这样的格子 —— 否则等哪天指南那三张现场照也补齐了，这条会变成空跑。
        """
        self.login()
        body = self.client.get(reverse("core:recruit")).content.decode()

        empty_keys = []
        for tag in re.findall(r"<figure[^>]*>", body):
            if "is-empty" not in tag:
                continue
            m = re.search(r'data-slot-key="([^"]+)"', tag)
            if m:
                empty_keys.append(m.group(1))

        self.assertTrue(empty_keys, "这一页一个空槽位都没有，这条断言没测到东西")
        for key in empty_keys:
            self.assertIn(key, slot_registry.REGISTRY)
            self.assertIn(f"{self.url}?key={key}", body)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="esta-test-video-"))
class MediaSlotVideoFormTests(TestCase):
    """视频槽在素材中心里的表单行为。

    最重要的一条是「图片槽看不到视频字段」：登记表是权威，哪个位置放什么由代码
    决定。若每个槽位都露出视频输入框，站务会以为随便哪里都能放视频，而那些位置
    的模板根本不会渲染 <video> —— 传上去毫无反应，又是一个不报错的故障。
    """

    VIDEO_KEY = "home.movie.teaser"
    IMAGE_KEY = "home.gallery.lab"

    def setUp(self):
        cache.clear()
        self.url = reverse("dashboard:media_slots")
        self.officer = User.objects.create_user(username="vofficer", password="x")
        self.officer.set_level(roles.LEVEL_OFFICER)
        self.client.login(username="vofficer", password="x")

    def _post(self, key, **fields):
        prefix = key.replace(".", "_")
        data = {"action": "save", "key": key,
                f"{prefix}-focal_x": 50, f"{prefix}-focal_y": 50,
                f"{prefix}-is_active": "on"}
        data.update({f"{prefix}-{k}": v for k, v in fields.items()})
        return self.client.post(self.url, data, follow=True)

    def test_video_slot_form_exposes_video_fields(self):
        body = self.client.get(self.url).content.decode()
        prefix = self.VIDEO_KEY.replace(".", "_")
        self.assertIn(f'name="{prefix}-video_mp4"', body)
        self.assertIn(f'name="{prefix}-video_webm"', body)

    def test_image_slot_form_hides_video_fields(self):
        body = self.client.get(self.url).content.decode()
        prefix = self.IMAGE_KEY.replace(".", "_")
        self.assertNotIn(f'name="{prefix}-video_mp4"', body)
        self.assertNotIn(f'name="{prefix}-video_webm"', body)

    def test_video_slot_is_marked_in_the_listing(self):
        resp = self.client.get(self.url)
        self.assertContains(resp, "视频</span>")

    def test_uploading_a_clip_shows_up_on_the_public_page(self):
        self._post(self.VIDEO_KEY, image=make_png("c.png"),
                   video_mp4=make_mp4(), alt="片头循环")
        obj = MediaSlot.objects.get(key=self.VIDEO_KEY)
        self.assertTrue(obj.has_video)
        self.assertEqual(len(obj.video_sources), 1)

        self.client.logout()
        body = self.client.get(reverse("core:home")).content.decode()
        self.assertIn("<video", body)
        self.assertIn('type="video/mp4"', body)

    def test_wrong_extension_is_rejected(self):
        """扩展名直接进 <source type=...>，传错了浏览器只会静默不播。"""
        resp = self._post(self.VIDEO_KEY, image=make_png("c.png"),
                          video_mp4=make_mp4("clip.mov"))
        self.assertContains(resp, "保存失败")
        self.assertFalse(MediaSlot.objects.filter(key=self.VIDEO_KEY).exists())

    def test_oversized_file_is_rejected_with_a_reason(self):
        big = make_mp4("big.mp4", size=7 * 1024 * 1024)
        resp = self._post(self.VIDEO_KEY, image=make_png("c.png"), video_mp4=big)
        self.assertContains(resp, "保存失败")
        self.assertContains(resp, "上限")
        self.assertFalse(MediaSlot.objects.filter(key=self.VIDEO_KEY).exists())

    def test_file_over_recommendation_saves_but_warns(self):
        """判断「这段画面值不值这么多流量」是人的事，但得让他知道传了多大。"""
        chunky = make_mp4("chunky.mp4", size=2 * 1024 * 1024)
        resp = self._post(self.VIDEO_KEY, image=make_png("c.png"), video_mp4=chunky)
        self.assertTrue(MediaSlot.objects.filter(key=self.VIDEO_KEY).exists())
        self.assertContains(resp, "超过建议体积")

    def test_poster_only_is_a_valid_save(self):
        self._post(self.VIDEO_KEY, image=make_png("c.png"), alt="只有封面")
        obj = MediaSlot.objects.get(key=self.VIDEO_KEY)
        self.assertFalse(obj.has_video)
        self.assertEqual(obj.alt, "只有封面")

    def test_replacing_only_the_caption_keeps_the_clip(self):
        obj = MediaSlot.objects.create(
            key=self.VIDEO_KEY, image=make_png("c.png"), video_mp4=make_mp4(),
        )
        original = obj.video_mp4.name
        self._post(self.VIDEO_KEY, caption="改了图注")
        obj.refresh_from_db()
        self.assertEqual(obj.caption, "改了图注")
        self.assertEqual(obj.video_mp4.name, original)


class PositionManageTests(TestCase):
    """职位管理：自建职位、保护固定职位、以及「任命 ≠ 上墙」这条边界。"""

    def setUp(self):
        self.admin = User.objects.create_user(username="posadmin", password="x")
        self.admin.set_level(roles.LEVEL_ADMIN)
        self.client.login(username="posadmin", password="x")
        self.member = User.objects.create_user(username="posmember", password="x")
        self.member.set_level(roles.LEVEL_FORMAL)

    def test_admin_can_create_a_custom_position(self):
        """不能自建职位的话这一页只能容下五个主席，「干事墙」就无从存在。"""
        self.client.post(reverse("dashboard:positions"), {
            "form": "create", "name": "硬件部长", "blurb": "带硬件培训",
            "color": "#41d8e8", "sort_order": "60",
        })
        pos = Position.objects.get(name="硬件部长")
        self.assertEqual(pos.blurb, "带硬件培训")
        self.assertEqual(pos.sort_order, 60)

    def test_custom_positions_never_grant_dashboard_access(self):
        """自建职位不开提权入口：要站务权限就走等级变更，那条路有日志有通知。"""
        self.client.post(reverse("dashboard:positions"), {
            "form": "create", "name": "宣传干事", "grants_management": "on",
        })
        self.assertFalse(Position.objects.get(name="宣传干事").grants_management)

    def test_bogus_color_falls_back_instead_of_reaching_the_style_attribute(self):
        """颜色会直接进模板的 style 属性，只放行标准六位十六进制值。"""
        self.client.post(reverse("dashboard:positions"), {
            "form": "create", "name": "测试职位", "color": "red; background:url(x)",
        })
        self.assertEqual(Position.objects.get(name="测试职位").color, "#0da9cd")

    def test_fixed_positions_cannot_be_deleted(self):
        """`returning_review()` 按名字 update_or_create 这五个 —— 删掉之后下一次
        审核会静默再建一个，团队页上就出现两个同名分组。"""
        chair = Position.objects.get(name="主席")
        self.client.post(reverse("dashboard:positions"), {
            "form": "delete", "position_id": chair.pk,
        })
        self.assertTrue(Position.objects.filter(pk=chair.pk).exists())

    def test_custom_position_delete_clears_holders_without_touching_accounts(self):
        pos = Position.objects.create(name="临时职位")
        self.member.position = pos
        self.member.save(update_fields=["position"])
        self.client.post(reverse("dashboard:positions"), {
            "form": "delete", "position_id": pos.pk,
        })
        self.member.refresh_from_db()
        self.assertIsNone(self.member.position)
        self.assertTrue(self.member.is_active)
        self.assertEqual(self.member.member_level, roles.LEVEL_FORMAL)

    def test_assigning_a_position_does_not_publish_the_person(self):
        """**这条是本任务的核心边界。** 站务任命一个人，不等于替他同意公开展示 ——
        公开姓名和照片是本人的同意，注册时那份隐私同意书里没有这一条。
        """
        chair = Position.objects.get(name="主席")
        self.client.post(reverse("dashboard:positions"), {
            "form": "assign", "position_id": chair.pk, "user_id": self.member.pk,
            # 就算 POST 里带上也不该生效：这一页压根不处理这个字段
            "show_on_team": "on",
        })
        self.member.refresh_from_db()
        self.assertEqual(self.member.position, chair)
        self.assertFalse(self.member.show_on_team)
        self.assertNotIn(self.member, User.team())

    # ---- 任命表单要认人手上真有的标识 ----
    #
    # 真实故障：这一格原来叫「成员 ID」、按 `pk` 硬查，而页面上唯一看得见的成员
    # 标识是学号。管理员填学号 `2024000015` 直接 404（合法整数 → 查 id=2024000015
    # → 查不到 → Http404），填用户名是 500（非数字进 `pk=` 抛 ValueError）。
    # 而**既有的两条测试都从 ORM 对象取 `.pk` 来提交**，浏览器脚本更是用 evaluate
    # 直接往 DOM 里灌 pk —— 于是「站务从页面上拿不到这个数字」这件事在自动化里
    # 天生不可能暴露。下面这几条补的就是「真人会填什么」。

    def _assign(self, value, position="主席"):
        pos = Position.objects.get(name=position)
        return self.client.post(reverse("dashboard:positions"), {
            "form": "assign", "position_id": pos.pk, "user_id": value,
        }, follow=True)

    def test_assign_accepts_a_student_id(self):
        """**用户真踩到的那一条。** 学号是这一页上唯一看得见的成员标识。"""
        self.member.student_id = "2024000015"
        self.member.save(update_fields=["student_id"])
        resp = self._assign("2024000015")
        self.assertEqual(resp.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.position, Position.objects.get(name="主席"))

    def test_assign_accepts_a_username(self):
        """原来这一条是 500：非数字进 `pk=` 会让 IntegerField 抛 ValueError。"""
        resp = self._assign("posmember")
        self.assertEqual(resp.status_code, 200)
        self.member.refresh_from_db()
        self.assertIsNotNone(self.member.position)

    def test_assign_accepts_the_hash_id_printed_in_the_holders_table(self):
        """「现任职成员」表里显示的是 #pk，那个值填回来必须认。"""
        self._assign(f"#{self.member.pk}")
        self.member.refresh_from_db()
        self.assertIsNotNone(self.member.position)

    def test_assign_with_an_unknown_value_explains_instead_of_404(self):
        """404 会把已经选好的职位一起丢掉，而且页面上没有任何线索说该填什么。"""
        resp = self._assign("2024999999")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("没找到", resp.content.decode())
        self.member.refresh_from_db()
        self.assertIsNone(self.member.position)

    def test_failed_assignment_preserves_the_member_and_position(self):
        pos = Position.objects.get(name="主席")
        resp = self._assign("unknown-member")
        self.assertContains(resp, 'name="user_id" required value="unknown-member"')
        self.assertContains(resp, f'<option value="{pos.pk}" selected>')

    def test_invalid_position_id_explains_without_changing_the_member(self):
        for value in ("", "missing", "²", "9" * 30, "99999999"):
            with self.subTest(value=value):
                resp = self.client.post(reverse("dashboard:positions"), {
                    "form": "assign", "position_id": value, "user_id": self.member.username,
                }, follow=True)
                self.assertContains(resp, "请选择职位")
                self.member.refresh_from_db()
                self.assertIsNone(self.member.position)

    def test_invalid_identifier_is_html_escaped_when_redisplayed(self):
        resp = self._assign('<img src=x onerror=alert(1)>')
        self.assertContains(resp, '&lt;img src=x onerror=alert(1)&gt;')
        self.assertNotContains(resp, '<img src=x onerror=alert(1)>')

    def test_assign_refuses_to_guess_between_people_with_the_same_name(self):
        """`real_name` 没有唯一约束。挑错就是把职位任命到另一个人头上，
        而页面会显示「已任命」—— 所以认不准时必须问清楚，不能猜。"""
        self.member.real_name = "张三"
        self.member.student_id = "2024000001"
        self.member.save(update_fields=["real_name", "student_id"])
        other = User.objects.create_user(username="posmember2", password="x",
                                         real_name="张三", student_id="2024000002")
        resp = self._assign("张三")
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("2 个人叫", body)
        self.assertIn("posmember2", body)          # 把候选人列出来才叫说清楚
        self.member.refresh_from_db()
        other.refresh_from_db()
        self.assertIsNone(self.member.position)
        self.assertIsNone(other.position)

    def test_assign_warns_when_the_account_is_deactivated(self):
        """停用账号任命成功了也不会上墙，不说一句的话站务会以为团队页坏了。"""
        self.member.is_active = False
        self.member.save(update_fields=["is_active"])
        resp = self._assign("posmember")
        self.assertIn("停用", resp.content.decode())

    def test_unassign_still_works_with_the_pk_the_template_posts(self):
        """解除任命的隐藏字段发的是裸 pk，换了解析口径之后它必须照旧能用。"""
        chair = Position.objects.get(name="主席")
        self.member.position = chair
        self.member.save(update_fields=["position"])
        self.client.post(reverse("dashboard:positions"), {
            "form": "unassign", "user_id": self.member.pk,
        }, follow=True)
        self.member.refresh_from_db()
        self.assertIsNone(self.member.position)

    def test_unassign_does_not_confuse_a_hidden_pk_with_another_username(self):
        chair = Position.objects.get(name="主席")
        self.member.position = chair
        self.member.save(update_fields=["position"])
        other = User.objects.create_user(username=str(self.member.pk), password="x", position=chair)
        self.client.post(reverse("dashboard:positions"), {
            "form": "unassign", "user_id": self.member.pk,
        }, follow=True)
        self.member.refresh_from_db()
        other.refresh_from_db()
        self.assertIsNone(self.member.position)
        self.assertEqual(other.position, chair)

    def test_unassign_accepts_an_explicit_hash_id(self):
        chair = Position.objects.get(name="主席")
        self.member.position = chair
        self.member.save(update_fields=["position"])
        resp = self.client.post(reverse("dashboard:positions"), {
            "form": "unassign", "user_id": f"#{self.member.pk}",
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.member.refresh_from_db()
        self.assertIsNone(self.member.position)

    def test_non_admin_cannot_assign_a_position(self):
        self.client.force_login(self.member)
        resp = self.client.post(reverse("dashboard:positions"), {
            "form": "assign", "position_id": Position.objects.get(name="主席").pk,
            "user_id": self.member.username,
        })
        self.assertEqual(resp.status_code, 403)
        self.member.refresh_from_db()
        self.assertIsNone(self.member.position)

    def test_page_shows_who_still_needs_to_opt_in(self):
        """没有这个提示，站务任命完只会以为团队页坏了。"""
        chair = Position.objects.get(name="主席")
        self.member.position = chair
        self.member.save(update_fields=["position"])
        body = self.client.get(reverse("dashboard:positions")).content.decode()
        self.assertIn('data-optin="off"', body)
        self.assertIn(reverse("team:wall"), body)

    def test_position_list_is_ordered_by_sort_order(self):
        """`annotate(Count(...))` 会建 GROUP BY，而带 GROUP BY 的查询**不再套用
        `Meta.ordering`** —— 生成的 SQL 里压根没有 ORDER BY，列表变成数据库返回的
        任意顺序，页面照常渲染、没有任何报错。实测这一页曾经把「硬件副主席(40)」
        排在「软件主席(30)」前面。职位顺序就是团队页上的卡片顺序，所以这条要钉住。
        """
        Position.objects.create(name="末位职位", sort_order=999)
        body = self.client.get(reverse("dashboard:positions")).content.decode()
        seen = [
            (name, body.index(f">{name}<"))
            for name in Position.objects.values_list("name", flat=True)
            if f">{name}<" in body
        ]
        by_sort = list(
            Position.objects.order_by("sort_order", "id").values_list("name", flat=True)
        )
        self.assertEqual([name for name, _ in sorted(seen, key=lambda p: p[1])],
                         [n for n in by_sort if any(n == s for s, _ in seen)])

    def test_inactive_holder_is_not_shown_as_published(self):
        """停用账号无论勾没勾都不会上墙，显示「已公开」是误导。"""
        chair = Position.objects.get(name="主席")
        self.member.position = chair
        self.member.show_on_team = True
        self.member.is_active = False
        self.member.save(update_fields=["position", "show_on_team", "is_active"])
        body = self.client.get(reverse("dashboard:positions")).content.decode()
        self.assertIn("账号已停用", body)
        self.assertNotIn('data-optin="on"', body)

    def test_officer_level_cannot_reach_position_management(self):
        """职位任命是管理员的事（其中三个职位自带驾驶舱权限）。"""
        officer = User.objects.create_user(username="posofficer", password="x")
        officer.set_level(roles.LEVEL_OFFICER)
        self.client.login(username="posofficer", password="x")
        self.assertEqual(self.client.get(reverse("dashboard:positions")).status_code, 403)
