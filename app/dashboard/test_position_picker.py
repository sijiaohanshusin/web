from django.test import TestCase
from django.urls import reverse

from accounts import roles
from accounts.models import Position, User


class PositionMemberSearchTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="picker_admin", is_staff=True)
        self.client.force_login(self.admin)
        self.chair = Position.objects.get(name="主席")
        self.member = User.objects.create_user(
            username="hardware_chen", real_name="陈同学", student_id="2099000101",
            grade="2024", college="信息与通信工程学院", member_level=roles.LEVEL_FORMAL,
            phone="13800001111", email="private@example.invalid",
        )
        self.other = User.objects.create_user(
            username="software_chen", real_name="陈同学", student_id="2099000102",
            grade="2025", college="计算机科学与技术学院", position=self.chair,
            member_level=roles.LEVEL_FORMAL,
        )

    def search(self, **params):
        return self.client.get(reverse("dashboard:position_members"), params)

    def ids(self, response):
        self.assertEqual(response.status_code, 200)
        return [member["id"] for member in response.json()["members"]]

    def test_partial_name_returns_all_namesakes(self):
        self.assertCountEqual(self.ids(self.search(q="陈")), [self.member.pk, self.other.pk])

    def test_partial_username_and_student_id(self):
        self.assertEqual(self.ids(self.search(q="HARDWARE")), [self.member.pk])
        self.assertEqual(self.ids(self.search(q="000101")), [self.member.pk])

    def test_explicit_username_and_internal_id(self):
        self.assertEqual(self.ids(self.search(q="@hardware")), [self.member.pk])
        self.assertEqual(self.ids(self.search(q=f"#{self.member.pk}")), [self.member.pk])

    def test_filters_compose_with_search(self):
        response = self.search(q="陈", grade="2024", college=self.member.college, position="unassigned")
        self.assertEqual(self.ids(response), [self.member.pk])
        self.assertEqual(self.ids(self.search(position=self.chair.pk)), [self.other.pk])
        self.assertEqual(self.ids(self.search(q="陈", grade="2023")), [])

    def test_result_is_bounded_and_reports_more(self):
        User.objects.bulk_create([User(username=f"candidate_{n}") for n in range(15)])
        response = self.search(q="candidate_").json()
        self.assertEqual(len(response["members"]), 12)
        self.assertTrue(response["has_more"])

    def test_candidates_do_not_disclose_contacts_or_private_profile_fields(self):
        response = self.search(q="hardware").json()
        self.assertEqual(set(response["members"][0]), {
            "id", "username", "name", "student_id", "grade", "college", "position", "term", "is_active",
        })
        self.assertNotIn(self.member.phone, str(response))
        self.assertNotIn(self.member.email, str(response))

    def test_cache_is_disabled(self):
        self.assertIn("no-store", self.search(q="陈")["Cache-Control"])

    def test_invalid_filters_are_rejected(self):
        for params in ({"grade": "wrong"}, {"college": "wrong"}, {"position": "²"},
                       {"position": "9" * 30}, {"q": "x" * 151}):
            with self.subTest(params=params):
                self.assertEqual(self.search(**params).status_code, 400)

    def test_only_admins_can_search_members(self):
        for level in (roles.LEVEL_APPLICANT, roles.LEVEL_FORMAL, roles.LEVEL_OFFICER):
            with self.subTest(level=level):
                self.member.member_level = level
                self.member.save(update_fields=["member_level"])
                self.client.force_login(self.member)
                self.assertEqual(self.search(q="陈").status_code, 403)
        self.client.logout()
        self.assertEqual(self.search(q="陈").status_code, 302)

    def test_search_is_read_only(self):
        response = self.client.post(reverse("dashboard:position_members"), {"q": "陈"})
        self.assertEqual(response.status_code, 405)
        self.member.refresh_from_db()
        self.assertIsNone(self.member.position)

    def test_position_page_loads_the_picker_without_changing_the_post_contract(self):
        response = self.client.get(reverse("dashboard:positions"))
        self.assertContains(response, reverse("dashboard:position_members"))
        self.assertContains(response, "position-picker.js")
        self.assertContains(response, 'name="user_id"')
        self.assertContains(response, 'id="assign-member"')
