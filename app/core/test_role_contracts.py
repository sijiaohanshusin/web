"""Cross-page access contracts, shared by Django and local browser checks."""
from django.test import Client, TestCase

from accounts.models import Position, User

ROLE_LEVELS = {
    "guest": None, "pending": 0, "recruit": 1, "preparatory": 2,
    "member": 3, "vicechair": 3, "chair": 3, "officer": 4, "admin": 5,
}
ROUTES = {
    "/": "public", "/recruit/": "public", "/recruitment/": "public",
    "/news/": "public", "/events/": "public", "/resources/": "public",
    "/works/": "public", "/honors/": "public", "/team/": "public",
    "/help/": "public", "/help/recruit/": "public", "/help/member/": "public",
    "/accounts/profile/": "authenticated", "/accounts/profile/edit/": "authenticated",
    "/notify/": "authenticated", "/points/": "member",
    "/projects/": "member", "/accounts/showcase/": "showcase",
    "/dashboard/": "officer", "/dashboard/members/": "officer",
    "/dashboard/recruitment/": "officer", "/dashboard/news/": "officer",
    "/dashboard/events/": "officer", "/dashboard/resources/": "officer",
    "/dashboard/projects/": "officer", "/dashboard/honors/": "officer",
    "/dashboard/media/": "officer", "/dashboard/feedbacks/": "officer",
    "/dashboard/positions/": "admin", "/dashboard/medals/": "admin",
    "/dashboard/site/": "admin", "/help/admin/": "internal-officer",
    "/help/admin/members/": "internal-officer", "/help/admin/settings/": "internal-admin",
    "/help/admin/positions/": "internal-admin",
}


def expected_status(role, rule):
    if rule == "public":
        return 200
    anonymous = role in {"guest", "pending"}
    if rule.startswith("internal-"):
        allowed = role == "admin" or (rule == "internal-officer" and role in {"chair", "officer"})
        return 200 if allowed else 404
    if anonymous:
        return 302
    allowed = {
        "authenticated": True,
        "member": role not in {"recruit"},
        "showcase": role not in {"recruit", "preparatory"},
        "officer": role in {"chair", "officer", "admin"},
        "admin": role == "admin",
    }[rule]
    return 200 if allowed else 403


def make_roles(prefix, password):
    users = {"guest": None}
    for role, level in ROLE_LEVELS.items():
        if role == "guest":
            continue
        position = None
        if role in {"chair", "vicechair"}:
            position = Position.objects.get(name="主席" if role == "chair" else "硬件副主席")
        users[role] = User.objects.create_user(
            username=f"{prefix}-{role}", password=password,
            real_name=f"体验验收 {role}", member_level=level,
            is_active=role != "pending", is_staff=role == "admin", position=position,
        )
    return users


class CrossPageRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = make_roles("route-contract", "RouteTest-Only-2026!")

    def test_catalog_matches_server_permissions_for_all_roles(self):
        for role, user in self.users.items():
            client = Client()
            if user:
                client.force_login(user)
            for url, rule in ROUTES.items():
                with self.subTest(role=role, url=url):
                    response = client.get(url)
                    self.assertEqual(response.status_code, expected_status(role, rule))
                    if response.status_code == 302:
                        self.assertTrue(response.url.startswith('/accounts/login/'))

    def test_internal_search_never_exposes_unavailable_tasks(self):
        for role, user in self.users.items():
            client = Client()
            if user:
                client.force_login(user)
            for query, slug, rule in (
                ("站点设置", "settings", "internal-admin"),
                ("会员管理", "members", "internal-officer"),
            ):
                with self.subTest(role=role, query=query):
                    response = client.get('/help/search/', {'q': query})
                    target = f'/help/admin/{slug}/'
                    if expected_status(role, rule) == 200:
                        self.assertContains(response, target)
                    else:
                        self.assertNotContains(response, target)
