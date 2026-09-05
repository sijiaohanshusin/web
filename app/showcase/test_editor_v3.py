import copy
import json
import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from projects.models import Project
from .models import Showcase
from .rendering import public_member
from .schema import upgrade_design, validate_design
from .services import add_asset, change, get_showcase
from . import tests as fixtures
from .tests import Client, upload_image


class EditorV3Tests(TestCase):
    client_class = Client
    setUp = fixtures.ShowcaseTests.setUp
    send = fixtures.ShowcaseTests.send
    publish = fixtures.ShowcaseTests.publish
    public = fixtures.ShowcaseTests.public
    asset_url = fixtures.ShowcaseTests.asset_url

    def work(self, **extra):
        return {"id": str(uuid.uuid4()), "title": "独立作品", "description": "作品说明",
                "image": "", "url": "", "project": "", **extra}

    def state(self):
        return self.client.get(reverse("accounts:showcase_state"))

    def test_state_is_owner_only_and_has_no_account_private_fields(self):
        data = self.state().json()
        self.assertEqual(data["revision"], self.sc.revision)
        self.assertEqual(data["draft"]["version"], 4)
        for field in ("real_name", "student_id", "email", "phone", "qq", "birthday"):
            self.assertNotIn(field, json.dumps(data))
        other = User.objects.create_user(username="state-owner", member_level=3)
        self.client.force_login(other)
        self.assertEqual(self.state().json()["draft"]["nickname"], "")
        self.assertFalse(Showcase.objects.filter(user=other).exists())

    def test_state_requires_eligible_login_and_is_never_cached(self):
        response = self.state()
        self.assertIn("no-store", response["Cache-Control"])
        self.client.logout()
        self.assertEqual(self.state().status_code, 302)
        recruit = User.objects.create_user(username="state-recruit", member_level=1)
        self.client.force_login(recruit)
        self.assertEqual(self.state().status_code, 403)

    def test_v2_ids_are_deterministic_without_rewriting_snapshot(self):
        old = copy.deepcopy(self.data)
        old["version"] = 2
        old["card"].pop("featured_work")
        item = self.work()
        item.pop("id")
        old["content"]["works"] = [item]
        first, second = upgrade_design(old), upgrade_design(old)
        self.assertEqual(first, second)
        self.assertEqual(first["card"]["featured_work"], first["content"]["works"][0]["id"])
        self.assertNotIn("id", old["content"]["works"][0])
        self.assertEqual(old["version"], 2)

    def test_selected_work_survives_reorder_and_description_edit(self):
        first, second = self.work(title="甲"), self.work(title="乙")
        self.data["content"]["works"] = [first, second]
        self.data["card"].update(featured_work=second["id"], modules=["work"])
        self.data["content"]["works"].reverse()
        second["description"] = "新描述"
        validated = validate_design(self.data)
        dto = public_member(self.sc, validated)
        self.assertEqual(dto["featured_work"]["title"], "乙")
        self.assertEqual(dto["featured_work"]["id"], second["id"])
        self.assertIn("乙", self.send("preview").json()["document"])

    def test_removed_selected_work_is_rejected_instead_of_silently_replaced(self):
        work = self.work()
        self.data["card"]["featured_work"] = work["id"]
        response = self.send("save")
        self.assertEqual(response.status_code, 400)
        self.assertIn("card.featured_work", response.json()["fields"])

    def test_selected_project_uses_canonical_url_and_never_falls_back_when_private(self):
        project = Project.objects.create(name="公开实验板", is_public=True)
        image = add_asset(self.user, upload_image())
        first = self.work(title="不应自动替换的作品")
        selected = self.work(title="", project=str(project.pk), image=str(image.pk), url="https://example.com/conflict")
        self.data["content"]["works"] = [first, selected]
        self.data["card"].update(featured_work=selected["id"], modules=["work"])
        self.data["page"]["modules"] = []
        validated = validate_design(self.data)
        self.assertEqual(validated["content"]["works"][1]["url"], "")
        self.assertEqual(public_member(self.sc, validated)["featured_work"]["url"], project.public_url)
        self.data = validated
        self.publish()
        project.is_public = False
        project.save(update_fields=["is_public"])
        self.sc.refresh_from_db()
        self.assertIsNone(public_member(self.sc, self.sc.published)["featured_work"])
        self.assertNotContains(self.public(), "精选作品 /")
        self.assertEqual(Client().get(self.asset_url(image)).status_code, 404)

    def test_six_works_can_be_saved_and_seventh_is_rejected_without_data_loss(self):
        self.data["content"]["works"] = [self.work(title=f"作品 {index}") for index in range(6)]
        self.assertEqual(self.send("save").status_code, 200)
        self.sc.refresh_from_db()
        self.data["content"]["works"].append(self.work())
        response = self.send("save")
        self.assertEqual(response.status_code, 400)
        self.assertIn("content.works", response.json()["fields"])
        self.assertEqual(len(self.state().json()["draft"]["content"]["works"]), 6)

    def test_duplicate_ids_and_unknown_work_fields_rejected(self):
        work = self.work()
        for works in ([work, work.copy()], [{**work, "css": "display:none"}]):
            self.data["content"]["works"] = works
            with self.assertRaises(ValidationError):
                validate_design(self.data)

    def test_selecting_no_work_does_not_fall_back_to_first(self):
        self.data["content"]["works"] = [self.work()]
        self.data["card"]["modules"] = ["work"]
        dto = public_member(self.sc, self.data)
        self.assertIsNone(dto["featured_work"])
        self.assertNotIn("精选作品 /", self.send("preview").json()["document"])

    def test_hidden_work_image_does_not_become_public(self):
        a = add_asset(self.user, upload_image())
        first, second = self.work(image=str(a.pk)), self.work(title="所选作品")
        self.data["content"]["works"] = [first, second]
        self.data["card"].update(featured_work=second["id"], modules=["work"])
        self.data["page"]["modules"] = []
        self.publish()
        self.assertEqual(Client().get(self.asset_url(a)).status_code, 404)
        self.assertNotIn(str(a.pk), self.public().content.decode())

    def test_hidden_background_stays_private_but_cannot_be_deleted(self):
        a = add_asset(self.user, upload_image())
        self.data["card"]["background"].update(mode="gradient", image=str(a.pk))
        self.publish()
        row = self.state().json()["assets"][0]
        self.assertEqual(row["public_uses"], [])
        self.assertEqual(row["draft_uses"], ["卡片背景"])
        self.assertFalse(row["can_delete"])
        self.assertEqual(Client().get(self.asset_url(a)).status_code, 404)

    def test_asset_metadata_reports_processed_format_and_size_not_storage_path(self):
        a = add_asset(self.user, upload_image(name="实验.png", size=(2000, 1000)))
        row = self.state().json()["assets"][0]
        self.assertEqual(row["format"], "JPEG")
        self.assertEqual(row["width"], 1600)
        self.assertEqual(row["height"], 800)
        self.assertEqual(row["bytes"], a.image.size)
        self.assertEqual(row["name"], "实验.jpg")
        self.assertNotIn(a.image.name, json.dumps(row))
        self.assertTrue(row["can_delete"])

    def test_old_asset_has_neutral_name_without_migration_side_effect(self):
        a = add_asset(self.user, upload_image())
        type(a).objects.filter(pk=a.pk).update(display_name="", byte_size=0)
        row = self.state().json()["assets"][0]
        self.assertEqual(row["name"], "素材 1.jpg")
        self.assertGreater(row["bytes"], 0)
        a.refresh_from_db()
        self.assertEqual(a.display_name, "")
        self.assertEqual(a.byte_size, 0)

    def test_preview_both_returns_two_components_without_saving(self):
        response = self.send("preview", target="both").json()
        self.assertIn("sc-card", response["documents"]["card"])
        self.assertIn("sc-page", response["documents"]["page"])
        self.assertTrue(response["ticket"])
        self.sc.refresh_from_db()
        self.assertIsNone(self.sc.published)
        self.assertNotEqual(self.sc.draft["nickname"], self.data["nickname"])

    def test_six_template_previews_do_not_change_data(self):
        response = self.send("preview", target="templates")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["documents"]), 6)
        self.assertNotIn("ticket", response.json())
        self.sc.refresh_from_db()
        self.assertIsNone(self.sc.published)
        self.assertEqual(self.sc.revision, 0)

    def test_error_paths_point_to_correct_field(self):
        self.data["content"]["intro"] = "长" * 61
        data = self.send("save").json()
        self.assertIn("content.intro", data["fields"])
        self.assertNotIn("Traceback", data["error"])

    def test_publication_revalidates_latest_preview_and_version(self):
        ticket = self.send("preview", target="both").json()["ticket"]
        saved = self.send("save").json()
        self.sc.refresh_from_db()
        response = self.send("publish", revision=saved["revision"], ticket=ticket, consent=True)
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(Showcase.objects.get(pk=self.sc.pk).published)

    def test_conflict_has_machine_code_and_does_not_overwrite(self):
        first = self.send("save")
        self.assertEqual(first.status_code, 200)
        self.data["nickname"] = "另一个标签页"
        second = self.send("save")
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["code"], "conflict")
        self.assertEqual(self.state().json()["draft"]["nickname"], "林序")

    def test_unsaved_and_saved_asset_references_are_distinct(self):
        a = add_asset(self.user, upload_image())
        self.data["content"]["avatar"] = str(a.pk)
        self.assertEqual(self.state().json()["assets"][0]["draft_uses"], [])
        self.send("save")
        row = self.state().json()["assets"][0]
        self.assertEqual(row["draft_uses"], ["展示头像"])
        self.assertEqual(row["public_uses"], [])
        self.assertFalse(row["can_delete"])

    def test_personal_page_three_layouts_share_full_image_links(self):
        a = add_asset(self.user, upload_image())
        self.data["content"]["works"] = [self.work(image=str(a.pk))]
        self.data["content"]["gallery"] = [{"image": str(a.pk), "caption": "图集"}]
        self.data["page"]["modules"] = ["works", "gallery"]
        for template in ("plate", "gallery", "type"):
            self.data["page"]["template"] = template
            doc = self.send("preview", target="page").json()["document"]
            self.assertIn("sc-page--" + template, doc)
            self.assertIn(self.asset_url(a, "large"), doc)
            self.assertNotIn(self.user.student_id, doc)

    def test_bespoke_templates_use_only_public_profile_fields(self):
        self.data["content"].update(intro="保持好奇，让想法发生。", about="公开介绍", skills="公开技能")
        self.data["page"]["modules"] = ["intro", "skills", "history"]
        expected = {
            "plate": ("sc-dossier-grid", "SPECIFICATION"),
            "type": ("sc-archive-layout", "IDENTITY COLOPHON"),
        }
        for template, markers in expected.items():
            self.data["page"]["template"] = template
            doc = self.send("preview", target="page").json()["document"]
            for marker in markers:
                self.assertIn(marker, doc)
            for private in (self.user.real_name, self.user.student_id, self.user.email, self.user.phone, self.user.qq):
                self.assertNotIn(private, doc)
        self.assertNotIn("LOCATION", doc)

    def test_complete_save_preview_publish_edit_withdraw_flow(self):
        a = add_asset(self.user, upload_image())
        self.data["content"]["avatar"] = str(a.pk)
        self.send("save")
        self.sc.refresh_from_db()
        ticket = self.send("preview", target="both").json()["ticket"]
        response = self.send("publish", consent=True, ticket=ticket)
        self.assertTrue(response.json()["published"])
        self.sc.refresh_from_db()
        self.assertEqual(self.public().status_code, 200)
        self.assertEqual(Client().get(self.asset_url(a)).status_code, 200)
        self.data["nickname"] = "新草稿"
        self.send("save")
        self.assertContains(self.public(), "林序")
        self.assertNotContains(self.public(), "新草稿")
        self.sc.refresh_from_db()
        self.send("withdraw")
        self.assertEqual(self.public().status_code, 404)
        self.assertEqual(Client().get(self.asset_url(a)).status_code, 404)
        self.assertEqual(self.state().json()["draft"]["nickname"], "新草稿")
