import copy
import importlib
import io
import json
import tempfile
import uuid
from datetime import date
from types import SimpleNamespace

from PIL import Image
from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client as DjangoClient, TestCase, override_settings
from django.urls import reverse

from accounts.models import Position, User
from projects.models import Project
from .models import ModerationEvent, Showcase, ShowcaseAsset
from .rendering import public_member
from .schema import empty_design, validate_design
from .services import Conflict, add_asset, change, get_showcase, moderate, preview_ticket


def upload_image(name="test.png", size=(64, 48), fmt="PNG", **options):
    output = io.BytesIO()
    Image.new("RGB", size, "#187c90").save(output, fmt, **options)
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/" + ("jpeg" if fmt == "JPEG" else fmt.lower()))


class Client(DjangoClient):
    def request(self, **request):
        response = super().request(**request)
        if response.streaming:
            # Exhausting Django's wrapper closes the file without closing the test transaction.
            data = b"".join(response.streaming_content)
            response.streaming_content = (data,)
        return response


class ShowcaseTests(TestCase):
    client_class = Client
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media.name, DEBUG=True)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media.cleanup)
        self.user = User.objects.create_user(username="private-login", real_name="私有档案姓名", member_level=3,
            student_id="2024999001", phone="13800000101", email="private-test@example.com", qq="99981234",
            gender="female", birthday=date(2004, 4, 18), grade="2024")
        self.sc = get_showcase(self.user)
        self.data = copy.deepcopy(self.sc.draft)
        self.data["nickname"] = "林序"
        self.data["content"].update(intro="让想法落地。", tags=["开源", "设计"])
        self.client.force_login(self.user)
        self.url = reverse("accounts:showcase_action")

    def send(self, action, **extra):
        data = {"action": action, "revision": self.sc.revision, "design": self.data}
        data.update(extra)
        return self.client.post(self.url, json.dumps(data), content_type="application/json")

    def publish(self, data=None):
        self.sc.refresh_from_db()
        data = data or self.data
        self.sc = change(self.user, "publish", self.sc.revision, data, True, preview_ticket(self.sc, data))

    def public(self):
        return Client().get(reverse("team:detail", args=[self.sc.pk]))

    def asset_url(self, asset, size="small"):
        return reverse("showcase:asset", args=[asset.pk, size])

    def test_formal_member_without_position_can_edit(self):
        self.assertIsNone(self.user.position)
        self.assertContains(self.client.get(reverse("accounts:showcase")), "设计我的展示")

    def test_no_automatic_publication_or_avatar_copy(self):
        self.assertIsNone(self.sc.published)
        self.assertEqual(self.sc.assets.count(), 0)
        self.assertEqual(self.public().status_code, 404)

    def test_draft_save_is_private(self):
        self.assertEqual(self.send("save").status_code, 200)
        self.sc.refresh_from_db()
        self.assertEqual(self.sc.draft["nickname"], "林序")
        self.assertIsNone(self.sc.published)
        self.assertNotContains(Client().get("/team/"), "林序")

    def test_preview_does_not_save_or_publish(self):
        response = self.send("preview")
        self.assertEqual(response.status_code, 200)
        self.assertIn("林序", response.json()["document"])
        self.sc.refresh_from_db()
        self.assertNotEqual(self.sc.draft["nickname"], "林序")
        self.assertIsNone(self.sc.published)

    def test_publish_requires_consent(self):
        self.assertEqual(self.send("publish", ticket=preview_ticket(self.sc, self.data)).status_code, 400)

    def test_publish_requires_preview(self):
        self.assertEqual(self.send("publish", consent=True).status_code, 400)

    def test_changed_design_invalidates_preview(self):
        ticket = self.send("preview").json()["ticket"]
        self.data["nickname"] = "Changed"
        self.assertEqual(self.send("publish", consent=True, ticket=ticket).status_code, 400)

    def test_publish_flow_and_public_uuid(self):
        preview = self.send("preview").json()
        self.assertEqual(self.send("publish", consent=True, ticket=preview["ticket"]).status_code, 200)
        self.assertContains(self.public(), "林序")
        self.assertEqual(uuid.UUID(str(self.sc.pk)).version, 4)

    def test_saving_after_publication_does_not_replace_snapshot(self):
        self.publish()
        self.data["nickname"] = "尚未公开的新昵称"
        self.assertEqual(self.send("save").status_code, 200)
        self.assertNotContains(self.public(), "尚未公开的新昵称")
        self.assertContains(self.public(), "林序")

    def test_withdraw_hides_wall_page_and_retains_draft(self):
        self.publish()
        self.assertEqual(self.send("withdraw").status_code, 200)
        self.assertEqual(self.public().status_code, 404)
        self.sc.refresh_from_db()
        self.assertEqual(self.sc.draft["nickname"], "林序")

    def test_stale_save_cannot_overwrite_newer_version(self):
        self.assertEqual(self.send("save").status_code, 200)
        self.data["nickname"] = "旧标签页"
        self.assertEqual(self.send("save").status_code, 409)
        self.sc.refresh_from_db()
        self.assertEqual(self.sc.draft["nickname"], "林序")

    def test_stale_withdraw_is_rejected(self):
        self.publish()
        self.assertEqual(self.send("withdraw", revision=0).status_code, 409)
        self.assertEqual(self.public().status_code, 200)

    def test_other_account_cannot_use_preview_ticket(self):
        other = User.objects.create_user(username="other", member_level=3)
        sc = get_showcase(other)
        with self.assertRaises(ValidationError):
            change(other, "publish", sc.revision, self.data, True, preview_ticket(self.sc, self.data))

    def test_applicant_and_preparatory_have_no_editor(self):
        for level in (0, 1, 2):
            user = User.objects.create_user(username=f"level{level}", member_level=level)
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("accounts:showcase")).status_code, 403)
            self.assertEqual(self.send("preview").status_code, 403)

    def test_inactive_account_cannot_access_editor(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(reverse("accounts:showcase")).status_code, 302)

    def test_post_csrf_is_required(self):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        response = strict.post(self.url, json.dumps({"action": "save"}), content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_no_private_fields_in_wall_page_or_dto(self):
        self.publish()
        payload = json.dumps(public_member(self.sc, self.sc.published), ensure_ascii=False)
        for response in (self.public(), Client().get("/team/")):
            payload += response.content.decode()
        for secret in (self.user.username, self.user.real_name, self.user.student_id, self.user.email, self.user.phone, self.user.qq, "2004-04-18", "female"):
            self.assertNotIn(secret, payload)

    def test_search_only_public_name_and_visible_tags(self):
        self.publish()
        for query in ("林序", "开源"):
            self.assertEqual(Client().get("/team/", {"q": query}).context["page"].paginator.count, 1)
        for query in (self.user.username, self.user.real_name, self.user.student_id, self.user.phone, self.user.email):
            self.assertEqual(Client().get("/team/", {"q": query}).context["page"].paginator.count, 0)

    def test_disabled_tags_not_indexed(self):
        self.data["card"]["modules"] = ["intro"]
        self.data["page"]["modules"] = ["intro"]
        self.publish()
        self.assertEqual(Client().get("/team/", {"q": "开源"}).context["page"].paginator.count, 0)

    def test_cohort_direction_position_filters(self):
        self.publish()
        self.assertEqual(Client().get("/team/", {"cohort": "2024", "direction": "hardware"}).context["page"].paginator.count, 1)
        self.assertEqual(Client().get("/team/", {"cohort": "2025"}).context["page"].paginator.count, 0)
        self.assertEqual(Client().get("/team/", {"position": "invalid"}).context["page"].paginator.count, 0)

    def test_pagination_and_order_not_position_rank(self):
        self.publish()
        for index in range(25):
            user = User.objects.create_user(username=f"page{index}", member_level=3, grade="2026")
            sc = get_showcase(user)
            data = sc.draft
            data["nickname"] = f"成员{index:02d}"
            change(user, "publish", 0, data, True, preview_ticket(sc, data))
        response = Client().get("/team/")
        self.assertEqual(len(response.context["members"]), 24)
        self.assertEqual(response.context["members"][0]["nickname"], "成员00")
        self.assertEqual(Client().get("/team/", {"page": 2}).context["members"][-1]["nickname"], "林序")

    def test_official_position_updates_live_and_unassignment_keeps_profile(self):
        self.publish()
        self.user.position = Position.objects.get(name="硬件副主席")
        self.user.position_term_start = 2025
        self.user.save()
        self.assertContains(self.public(), "硬件副主席")
        self.assertContains(self.public(), "2025")
        self.user.position = None
        self.user.save(update_fields=["position"])
        self.assertContains(self.public(), "林序")
        self.assertNotContains(self.public(), "硬件副主席")

    def test_history_opt_in_and_no_privilege_grant(self):
        self.user.position = Position.objects.get(name="硬件副主席")
        self.user.save()
        self.user.position = None
        self.user.save()
        self.publish()
        self.assertNotContains(self.public(), "历任")
        self.data["page"]["modules"] = ["history"]
        self.publish()
        self.assertContains(self.public(), "历任")
        self.user.refresh_from_db()
        self.assertEqual(self.user.member_level, 3)
        self.assertFalse(self.user.is_officer)

    def test_deactivation_requires_republication_on_reactivation(self):
        self.publish()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.public().status_code, 404)
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.public().status_code, 404)
        self.publish()
        self.assertEqual(self.public().status_code, 200)

    def test_bulk_demotion_revokes_publication_permanently(self):
        self.publish()
        User.objects.filter(pk=self.user.pk).update(member_level=2)
        User.objects.filter(pk=self.user.pk).update(member_level=3)
        self.assertEqual(self.public().status_code, 404)

    def test_bulk_update_deactivation_cannot_reactivate_publication(self):
        self.publish()
        self.user.is_active = False
        User.objects.bulk_update([self.user], ["is_active"])
        self.user.is_active = True
        User.objects.bulk_update([self.user], ["is_active"])
        self.assertEqual(self.public().status_code, 404)

    def test_moderation_blocks_publish_but_not_draft_edit(self):
        officer = User.objects.create_user(username="moderator", member_level=4)
        self.publish()
        moderate(officer, self.sc.pk, "hide", "请移除不当内容")
        self.sc.refresh_from_db()
        self.assertEqual(self.send("save").status_code, 200)
        self.sc.refresh_from_db()
        self.assertEqual(self.send("publish", consent=True, ticket=preview_ticket(self.sc, self.data)).status_code, 403)
        self.assertEqual(ModerationEvent.objects.count(), 1)
        moderate(officer, self.sc.pk, "unlock", "已核实")
        self.assertEqual(self.public().status_code, 404)
        self.publish()
        self.assertEqual(self.public().status_code, 200)

    def test_ordinary_member_cannot_moderate(self):
        self.assertEqual(self.client.get(reverse("showcase:moderation")).status_code, 403)
        with self.assertRaises(PermissionDenied):
            moderate(self.user, self.sc.pk, "hide", "test")

    def test_moderation_requires_reason(self):
        officer = User.objects.create_user(username="moderator", member_level=4)
        with self.assertRaises(ValidationError):
            moderate(officer, self.sc.pk, "hide", "")

    def test_html_is_escaped_in_shared_preview_and_public_render(self):
        self.data["content"]["about"] = '<script>alert(1)</script><img src="https://tracker.example/a">'
        self.publish()
        self.assertContains(self.public(), "&lt;script&gt;")
        self.assertNotContains(self.public(), '<img src="https://tracker.example/a">')
        preview = self.send("preview", target="page").json()["document"]
        self.assertIn("&lt;script&gt;", preview)
        self.assertNotIn("<script>", preview)

    def test_malformed_json_types_return_400_not_500(self):
        for key in ("cohort", "direction", "nickname", "card", "content"):
            bad = copy.deepcopy(self.data)
            bad[key] = []
            self.assertEqual(self.send("save", design=bad).status_code, 400)
        self.assertEqual(self.send([], design=self.data).status_code, 400)
        self.assertEqual(self.send("preview", target=[]).status_code, 400)

    def test_unknown_design_fields_and_raw_css_rejected(self):
        self.data["card"]["css"] = "body{display:none}"
        self.assertEqual(self.send("save").status_code, 400)

    def test_limits_are_enforced_server_side(self):
        for key, value in (("intro", "字" * 61), ("tags", ["a", "b", "c", "d", "e"]), ("works", [{}] * 7), ("gallery", [{}] * 7)):
            bad = copy.deepcopy(self.data)
            bad["content"][key] = value
            self.assertEqual(self.send("save", design=bad).status_code, 400)
        self.data["card"]["modules"] = ["intro", "tags", "work"]
        self.assertEqual(self.send("save").status_code, 400)

    def test_palette_and_module_whitelist(self):
        for key, value in (("template", "html"), ("palette", "red;url(x)"), ("modules", ["iframe"])):
            bad = copy.deepcopy(self.data)
            bad["card"][key] = value
            self.assertEqual(self.send("save", design=bad).status_code, 400)

    def test_official_title_cannot_be_nickname(self):
        self.data["nickname"] = "主席"
        self.assertEqual(self.send("save").status_code, 400)

    def test_https_links_only(self):
        for url in ("http://example.org", "javascript:alert(1)", "data:text/html,x", "https://user:pass@example.org"):
            self.data["content"]["links"] = [{"label": "test", "url": url}]
            self.assertEqual(self.send("save").status_code, 400)
        self.data["content"]["links"] = [{"label": "test", "url": "https://example.org"}]
        self.assertEqual(self.send("save").status_code, 200)

    def test_private_project_cannot_be_linked(self):
        project = Project.objects.create(name="私密项目", is_public=False)
        self.data["content"]["works"] = [{"title": "", "description": "", "image": "", "url": "", "project": str(project.pk)}]
        self.assertEqual(self.send("save").status_code, 400)

    def test_project_becoming_private_disappears(self):
        project = Project.objects.create(name="曾公开作品", is_public=True)
        self.data["content"]["works"] = [{"title": "", "description": "", "image": "", "url": "", "project": str(project.pk)}]
        self.publish()
        self.assertContains(self.public(), "曾公开作品")
        project.is_public = False
        project.save()
        self.assertNotContains(self.public(), "曾公开作品")

    def test_template_changes_preserve_content(self):
        self.data["content"]["about"] = "保留的文字"
        for template in ("plate", "gallery", "type"):
            self.sc.refresh_from_db()
            self.data["card"]["template"] = template
            self.assertEqual(self.send("save").status_code, 200)
            self.sc.refresh_from_db()
            self.assertEqual(self.sc.draft["content"]["about"], "保留的文字")

    def test_assets_private_until_actually_referenced_in_publication(self):
        asset = add_asset(self.user, upload_image())
        url = self.asset_url(asset)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(Client().get(url).status_code, 404)
        self.publish()
        self.assertEqual(Client().get(url).status_code, 404)
        self.data["content"]["avatar"] = str(asset.pk)
        self.publish()
        self.assertEqual(Client().get(url).status_code, 200)
        self.send("withdraw")
        self.assertEqual(Client().get(url).status_code, 404)

    def test_disabled_module_images_are_not_public(self):
        asset = add_asset(self.user, upload_image())
        self.data["content"]["gallery"] = [{"image": str(asset.pk), "caption": "未启用"}]
        self.publish()
        self.assertEqual(Client().get(self.asset_url(asset)).status_code, 404)

    def test_replaced_snapshot_retires_old_image(self):
        asset = add_asset(self.user, upload_image())
        self.data["content"]["avatar"] = str(asset.pk)
        self.publish()
        self.data["content"]["avatar"] = ""
        self.publish()
        self.assertEqual(Client().get(self.asset_url(asset)).status_code, 404)

    def test_raw_media_path_cannot_bypass_acl_even_in_debug(self):
        asset = add_asset(self.user, upload_image())
        self.assertEqual(Client().get("/media/" + asset.image.name).status_code, 403)

    def test_cross_member_asset_references_are_rejected(self):
        other = User.objects.create_user(username="other", member_level=3)
        get_showcase(other)
        asset = add_asset(other, upload_image())
        self.data["content"]["avatar"] = str(asset.pk)
        self.assertEqual(self.send("save").status_code, 400)
        self.assertEqual(self.client.get(self.asset_url(asset)).status_code, 404)
        self.assertEqual(self.client.post(reverse("accounts:showcase_asset_delete", args=[asset.pk])).status_code, 404)

    def test_exif_stripped_and_size_variants(self):
        exif = Image.Exif()
        exif[270] = "PRIVATE METADATA"
        asset = add_asset(self.user, upload_image("portrait.jpg", (2000, 1600), "JPEG", exif=exif))
        for field, maximum in ((asset.image, 1600), (asset.thumbnail, 640)):
            with field.open("rb") as file:
                image = Image.open(file)
                self.assertLessEqual(max(image.size), maximum)
                self.assertFalse(image.getexif())

    def test_spoofed_svg_and_animation_rejected(self):
        for upload in (SimpleUploadedFile("fake.png", b"<svg></svg>"), upload_image("fake.jpg")):
            with self.assertRaises(ValidationError):
                add_asset(self.user, upload)
        buf = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "WEBP", save_all=True, append_images=[Image.new("RGB", (10, 10), "red")], duration=100, loop=0)
        with self.assertRaises(ValidationError):
            add_asset(self.user, SimpleUploadedFile("animated.webp", buf.getvalue()))

    def test_oversized_pixel_and_file_limits(self):
        with self.assertRaises(ValidationError):
            add_asset(self.user, upload_image(size=(3000, 3000)))
        with self.assertRaises(ValidationError):
            add_asset(self.user, SimpleUploadedFile("big.png", b"x" * (5 * 1024 * 1024 + 1)))

    def test_twenty_asset_quota(self):
        ShowcaseAsset.objects.bulk_create([ShowcaseAsset(showcase=self.sc, image="showcase/fake.jpg", thumbnail="showcase/fake.jpg", width=1, height=1) for _ in range(20)])
        with self.assertRaises(ValidationError):
            add_asset(self.user, upload_image())

    def test_referenced_asset_cannot_be_deleted(self):
        asset = add_asset(self.user, upload_image())
        self.data["content"]["avatar"] = str(asset.pk)
        self.publish()
        response = self.client.post(reverse("accounts:showcase_asset_delete", args=[asset.pk]))
        self.assertEqual(response.status_code, 400)

    def test_copy_avatar_is_explicit_and_independent(self):
        self.user.avatar.save("account.png", upload_image())
        response = self.client.post(reverse("accounts:showcase_upload"), {"copy_avatar": "1"})
        self.assertEqual(response.status_code, 200)
        asset = self.sc.assets.get()
        self.assertNotEqual(asset.image.name, self.user.avatar.name)
        self.assertEqual(Client().get(self.asset_url(asset)).status_code, 404)

    def test_admin_cannot_read_private_asset(self):
        asset = add_asset(self.user, upload_image())
        admin = User.objects.create_superuser(username="admin", password="x")
        self.client.force_login(admin)
        self.assertEqual(self.client.get(self.asset_url(asset)).status_code, 404)

    def test_all_public_private_and_error_responses_no_store(self):
        asset = add_asset(self.user, upload_image())
        self.publish()
        for url in ("/team/", reverse("team:detail", args=[self.sc.pk]), reverse("accounts:showcase"), self.asset_url(asset), reverse("team:detail", args=[uuid.uuid4()])):
            response = self.client.get(url)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(response["CDN-Cache-Control"], "no-store")
        self.assertIn("noindex", self.public()["X-Robots-Tag"])

    @override_settings(DEBUG=False)
    def test_production_assets_use_internal_redirect(self):
        asset = add_asset(self.user, upload_image())
        response = self.client.get(self.asset_url(asset))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["X-Accel-Redirect"].startswith("/protected/showcase/"))

    def test_migration_preserves_only_previous_public_content(self):
        user = User.objects.create_user(username="legacy", real_name="原公开昵称", member_level=3,
            position=Position.objects.get(name="硬件副主席"), show_on_team=True, public_bio="原来公开的介绍", phone="13800000102")
        function = importlib.import_module("showcase.migrations.0002_adopt_consented_members").migrate_members
        function(apps, SimpleNamespace(connection=connection))
        function(apps, SimpleNamespace(connection=connection))
        sc = Showcase.objects.get(user=user)
        self.assertEqual(sc.published["nickname"], "原公开昵称")
        self.assertNotIn("history", sc.published["page"]["modules"])
        self.assertEqual(sc.published["content"]["links"], [])
        self.assertNotIn(user.phone, json.dumps(sc.published))
        self.assertEqual(Showcase.objects.filter(user=user).count(), 1)
        user.refresh_from_db()
        self.assertFalse(user.show_on_team, "Old rollback must not restore the retired consent switch")

    def test_migration_does_not_opt_in_new_members(self):
        user = User.objects.create_user(username="legacy-private", member_level=3, position=Position.objects.get(name="主席"), show_on_team=False)
        function = importlib.import_module("showcase.migrations.0002_adopt_consented_members").migrate_members
        function(apps, SimpleNamespace(connection=connection))
        self.assertFalse(Showcase.objects.filter(user=user).exists())

    def test_first_save_without_editor_get_does_not_crash(self):
        other = User.objects.create_user(username="direct-post", member_level=3)
        self.client.force_login(other)
        response = self.send("save", revision=0)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Showcase.objects.get(user=other).draft["nickname"], self.data["nickname"])

    def test_anonymous_write_is_rejected(self):
        self.client.logout()
        self.assertEqual(self.send("save").status_code, 302)

    def test_get_cannot_mutate_showcase(self):
        self.assertEqual(self.client.get(self.url, {"action": "publish"}).status_code, 405)
        self.sc.refresh_from_db()
        self.assertIsNone(self.sc.published)

    def test_deactivation_hides_images_and_cannot_implicitly_restore_them(self):
        asset = add_asset(self.user, upload_image())
        self.data["content"]["avatar"] = str(asset.pk)
        self.publish()
        self.assertEqual(Client().get(self.asset_url(asset)).status_code, 200)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        User.objects.filter(pk=self.user.pk).update(is_active=True)
        self.assertEqual(Client().get(self.asset_url(asset)).status_code, 404)

    def test_card_and_page_can_use_independent_templates(self):
        self.data["card"]["template"] = "gallery"
        self.data["page"]["template"] = "type"
        self.publish()
        self.assertContains(Client().get("/team/"), "sc-card--gallery")
        self.assertContains(self.public(), "sc-page--type")

    def test_no_raw_account_in_public_member_context(self):
        self.publish()
        member = self.public().context["member"]
        self.assertIsInstance(member, dict)
        self.assertNotIn("user", member)
        self.assertNotIn("id", member)

    def test_approved_palette_text_contrast(self):
        def luminance(color):
            channels = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
            channels = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
            return sum(c * weight for c, weight in zip(channels, (.2126, .7152, .0722)))
        for foreground in ("#65dfec", "#efb77a", "#d5dceb", "#b7c0c9", "#edf0f5"):
            self.assertGreaterEqual((luminance(foreground) + .05) / (luminance("#101316") + .05), 4.5)
