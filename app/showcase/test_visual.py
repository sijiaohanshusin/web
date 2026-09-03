import copy
import uuid
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from accounts.models import User
from .models import Showcase
from .rendering import public_member
from .schema import upgrade_design, validate_design
from .services import add_asset, get_showcase, change, moderate
from .tests import Client, ShowcaseTests, upload_image


class VisualTests(TestCase):
    client_class = Client
    setUp = ShowcaseTests.setUp
    send = ShowcaseTests.send
    publish = ShowcaseTests.publish
    public = ShowcaseTests.public
    asset_url = ShowcaseTests.asset_url

    def background(self, asset):
        self.data["card"]["background"].update(mode="photo", image=str(asset.pk))

    def test_three_modules_are_supported_but_not_four(self):
        self.data["card"]["modules"] = ["intro", "tags", "work"]
        self.assertEqual(self.send("save").status_code, 200)
        self.data["card"]["modules"].append("unknown")
        with self.assertRaises(ValidationError):
            validate_design(self.data)

    def test_background_choices_numbers_and_css_are_closed(self):
        for key, values in {"mode":[[],"url(x)"], "preset":["red",{}], "blur":["16px",4],
            "mask":["none",None], "x":[True,-1,101,"50%",float("nan")],
            "y":[-1,101,float("inf")], "zoom":[0.99,1.51,"1.2"], "image":["https://tracker.invalid/a.png",[]]}.items():
            for value in values:
                bad = copy.deepcopy(self.data)
                bad["card"]["background"][key] = value
                with self.subTest(key=key,value=value), self.assertRaises(ValidationError):
                    validate_design(bad)
        bad = copy.deepcopy(self.data)
        bad["card"]["background"]["css"] = "display:none"
        with self.assertRaises(ValidationError):
            validate_design(bad)

    def test_legacy_read_and_preview_never_rewrite_snapshots(self):
        asset = add_asset(self.user, upload_image())
        old = copy.deepcopy(self.data)
        old["version"] = 1
        del old["card"]["background"]
        old["card"].update(template="gallery", focus="top")
        old["content"]["cover"] = str(asset.pk)
        Showcase.objects.filter(pk=self.sc.pk).update(draft=old, published=old, public_name=old["nickname"])
        self.sc.refresh_from_db()
        dto = public_member(self.sc, old)
        self.assertEqual(dto["card"]["background"]["y"], 0)
        self.assertIn(str(asset.pk), dto["background"])
        self.assertEqual(Client().get(self.asset_url(asset)).status_code, 200)
        editor = self.client.get(reverse("accounts:showcase"))
        self.assertEqual(editor.context["bootstrap"]["draft"]["version"], 2)
        self.sc.refresh_from_db()
        self.assertEqual(self.sc.draft, old)
        self.assertEqual(self.sc.published, old)
        self.assertEqual(self.send("preview", design=old).status_code, 200)

    def test_legacy_malformed_input_is_validation_error(self):
        old = copy.deepcopy(self.data)
        old["version"] = 1
        del old["card"]["background"]
        old["content"] = []
        self.assertEqual(self.send("save", design=old).status_code, 400)
        old["card"] = []
        self.assertEqual(self.send("save", design=old).status_code, 400)

    def test_foreign_background_rejected_and_never_readable(self):
        other = User.objects.create_user(username="other-background", member_level=3)
        get_showcase(other)
        asset = add_asset(other, upload_image())
        self.background(asset)
        self.assertEqual(self.send("save").status_code, 400)
        self.assertEqual(self.send("preview").status_code, 400)
        self.assertEqual(self.client.get(self.asset_url(asset)).status_code, 404)

    def test_background_publish_save_and_withdraw_isolation(self):
        first = add_asset(self.user, upload_image())
        second = add_asset(self.user, upload_image())
        self.background(first)
        self.publish()
        self.assertEqual(Client().get(self.asset_url(first)).status_code, 200)
        self.background(second)
        self.assertEqual(self.send("save").status_code, 200)
        self.assertEqual(Client().get(self.asset_url(second)).status_code, 404)
        self.assertContains(Client().get("/team/"), self.asset_url(first))
        self.assertNotContains(Client().get("/team/"), str(second.pk))
        self.sc.refresh_from_db()
        change(self.user, "withdraw", self.sc.revision)
        self.assertEqual(Client().get(self.asset_url(first)).status_code, 404)

    def test_unused_background_and_personal_cover_remain_private(self):
        asset = add_asset(self.user, upload_image())
        self.data["card"]["background"]["image"] = str(asset.pk)
        self.data["content"]["cover"] = str(asset.pk)
        self.data["card"]["template"] = "gallery"
        self.publish()
        self.assertEqual(Client().get(self.asset_url(asset)).status_code, 404)
        self.assertNotContains(Client().get("/team/"), str(asset.pk))

    def test_background_removal_and_moderation_revoke_access(self):
        asset = add_asset(self.user, upload_image())
        self.background(asset)
        self.publish()
        self.data["card"]["background"]["mode"] = "gradient"
        self.publish()
        self.assertEqual(Client().get(self.asset_url(asset)).status_code, 404)
        self.background(asset)
        self.publish()
        admin = User.objects.create_superuser(username="visual-admin",password="test-only")
        moderate(admin, self.sc.pk,"hide","测试下架")
        self.assertEqual(Client().get(self.asset_url(asset)).status_code, 404)

    def test_background_cannot_be_deleted_while_draft_references_it(self):
        asset = add_asset(self.user, upload_image())
        self.background(asset)
        self.assertEqual(self.send("save").status_code, 200)
        response = self.client.post(reverse("accounts:showcase_asset_delete",args=[asset.pk]))
        self.assertEqual(response.status_code, 400)

    def test_public_wall_has_no_creation_or_management_controls(self):
        response = self.client.get("/team/")
        self.assertNotContains(response, "设计我的展示")
        self.assertNotContains(response, "展示内容管理")
        self.assertContains(response, "每一份热爱，都值得被认识")
        self.assertContains(response, "皖ICP备2026006667号")
        self.assertNotContains(response, "林序")

    def test_sort_filters_and_fragment_have_matching_results(self):
        self.data["cohort"] = "2025"
        self.publish()
        other = User.objects.create_user(username="earlier-public", member_level=3)
        sc = get_showcase(other)
        older = copy.deepcopy(self.data)
        older.update(nickname="另一位",cohort="2022")
        Showcase.objects.filter(pk=sc.pk).update(published=older, public_cohort="2022",public_name="另一位")
        for sort, expected in (("cohort_desc",["林序","另一位"]),("cohort_asc",["另一位","林序"])):
            response = Client().get("/team/", {"sort":sort})
            self.assertEqual([m["nickname"] for m in response.context["members"]],expected)
            part = Client().get("/team/", {"sort":sort},HTTP_X_SHOWCASE_PARTIAL="1")
            self.assertNotContains(part,"<html")
            self.assertEqual([m["nickname"] for m in part.context["members"]],expected)
            self.assertIn("no-store",part["Cache-Control"])
            self.assertIn("X-Showcase-Partial",part["Vary"])
        part = Client().get("/team/", {"q":"开源"},HTTP_X_SHOWCASE_PARTIAL="1")
        self.assertContains(part,'data-count="1"')
        for private in (self.user.real_name,self.user.username,self.user.student_id,self.user.email,self.user.phone):
            self.assertNotContains(part,private)

    @override_settings(DEBUG=False)
    def test_demo_helpers_fail_closed_in_production(self):
        from . import demo
        from django.http import Http404
        from django.test import RequestFactory
        request = RequestFactory().get("/team/design-demo/")
        for view,args in ((demo.samples,()),(demo.photo,("maker",)),(demo.sample_detail,(0,))):
            with self.assertRaises(Http404):
                view(request,*args)
