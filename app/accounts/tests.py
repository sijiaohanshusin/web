from datetime import date

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from . import roles, verification
from .models import Medal, Position, ReturningMembershipRequest, UserMedal, VerificationCode

User = get_user_model()

SSO_SECRET = "dev-sso-secret-not-for-production"


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegistrationTests(TestCase):
    def _register_payload(self, **over):
        data = {
            "username": "xiaoming",
            "real_name": "小明",
            "student_id": "2025010101",
            "college": "信息与通信工程学院",
            "grade": "2025",
            "email": "xm@example.com",
            "phone": "13800000001",
            "qq": "1081376858",
            "specialty": User.Specialty.HARDWARE,
            "specialty_custom": "",
            "privacy_consent": "on",
            "password1": "Str0ngPass!2025",
            "password2": "Str0ngPass!2025",
        }
        data.update(over)
        return data

    def _get_code(self, email, purpose):
        verification.issue(email, purpose)
        return VerificationCode.objects.filter(email=email, purpose=purpose, used=False).latest("created_at").code

    def test_register_requires_code(self):
        resp = self.client.post(reverse("accounts:register_new"), self._register_payload(code="000000"))
        self.assertContains(resp, "验证码")
        self.assertFalse(User.objects.filter(username="xiaoming").exists())

    def test_register_entry_offers_both_channels(self):
        """入口页必须同时给出两条通道的入口。

        断言的是**链接**而不是卡片上的文案 —— 文案会随改版一直变（原来叫
        「新会员通道」，现在叫「我是新同学」），而「两条路都能点进去」才是契约。
        """
        resp = self.client.get(reverse("accounts:register"))
        self.assertContains(resp, reverse("accounts:register_new"))
        self.assertContains(resp, reverse("accounts:register_returning"))
        self.assertIn("no-cache", resp.headers["Cache-Control"])

    def test_new_member_registers_active_at_recruit_level(self):
        code = self._get_code("xm@example.com", "register")
        resp = self.client.post(reverse("accounts:register_new"), self._register_payload(code=code))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("recruitment:index"))
        u = User.objects.get(username="xiaoming")
        self.assertTrue(u.is_active)
        self.assertEqual(u.member_level, roles.LEVEL_APPLICANT)
        self.assertEqual(u.registration_channel, User.RegistrationChannel.NEW)
        self.assertIn("_auth_user_id", self.client.session)

    def test_returning_member_waits_for_review(self):
        code = self._get_code("xm@example.com", "register")
        resp = self.client.post(reverse("accounts:register_returning"), self._register_payload(
            code=code,
            requested_role=ReturningMembershipRequest.RequestedRole.HARDWARE_VICE_CHAIR,
        ))
        self.assertEqual(resp.status_code, 200)
        u = User.objects.get(username="xiaoming")
        self.assertFalse(u.is_active)
        self.assertEqual(u.member_level, roles.LEVEL_PENDING)
        self.assertEqual(u.registration_channel, User.RegistrationChannel.RETURNING)
        self.assertEqual(
            u.returning_request.requested_role,
            ReturningMembershipRequest.RequestedRole.HARDWARE_VICE_CHAIR,
        )

    def test_custom_specialty_requires_description(self):
        resp = self.client.post(reverse("accounts:register_new"), self._register_payload(
            specialty=User.Specialty.CUSTOM,
            specialty_custom="",
            code="000000",
        ))
        self.assertContains(resp, "请填写具体方向")

    def test_grade_and_college_are_fixed_choices(self):
        resp = self.client.post(reverse("accounts:register_new"), self._register_payload(
            grade="2023级", college="信通学院", code="000000",
        ))
        self.assertContains(resp, "选择一个有效的选项", count=2)

    def test_duplicate_email_rejected(self):
        User.objects.create_user(username="a", password="x", email="dup@example.com")
        resp = self.client.post(reverse("accounts:register_new"), self._register_payload(email="dup@example.com", code="123456"))
        self.assertContains(resp, "该邮箱已注册")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegistrationNextTests(TestCase):
    """`?next=` 必须一路带过整条注册链路。

    从招新落地页点「注册」的人，注册完应该回到招新页。这个参数要过「选通道 →
    填表 → POST 回来重渲染」三跳，中间任何一跳丢了，用户就落到一个自己没要求
    去的地方 —— 而且没有任何报错。
    """

    def _payload(self, **over):
        data = {
            "username": "nextguy", "real_name": "小明", "student_id": "2025010199",
            "college": "信息与通信工程学院", "grade": "2025",
            "email": "next@example.com", "phone": "13800000099", "qq": "",
            "specialty": User.Specialty.HARDWARE, "specialty_custom": "",
            "privacy_consent": "on",
            "password1": "Str0ngPass!2025", "password2": "Str0ngPass!2025",
        }
        data.update(over)
        return data

    def test_choice_page_carries_next_into_both_channels(self):
        target = reverse("recruitment:index")
        resp = self.client.get(reverse("accounts:register"), {"next": target})
        body = resp.content.decode()
        self.assertIn(f"{reverse('accounts:register_new')}?next=", body)
        self.assertIn(f"{reverse('accounts:register_returning')}?next=", body)

    def test_form_page_keeps_next_in_a_hidden_field(self):
        """GET 带来的 next 要存进表单，否则 POST 回来就没了。"""
        resp = self.client.get(reverse("accounts:register_new"), {"next": "/events/"})
        self.assertContains(resp, 'name="next" value="/events/"')

    def test_registration_redirects_to_next(self):
        code = verification.issue("next@example.com", "register").code
        resp = self.client.post(reverse("accounts:register_new"),
                                self._payload(code=code, next="/events/"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/events/")

    def test_offsite_next_is_ignored(self):
        """开放重定向是真实漏洞：`?next=//evil.example` 必须当没传。"""
        code = verification.issue("next@example.com", "register").code
        resp = self.client.post(reverse("accounts:register_new"),
                                self._payload(code=code, next="//evil.example/"))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("recruitment:index"))

    def test_login_page_keeps_next(self):
        resp = self.client.get(reverse("accounts:login"), {"next": "/events/"})
        self.assertContains(resp, 'name="next" value="/events/"')

    def test_code_login_keeps_next(self):
        """验证码登录原来完全不认 next —— 从招新页切过来登录完就跳首页了。"""
        resp = self.client.get(reverse("accounts:code_login"), {"next": "/events/"})
        self.assertContains(resp, 'name="next" value="/events/"')


class AuthPagesNoStoreTests(TestCase):
    """账号链路的页面一律 `no-store`。

    站点前置 CDN，`DynamicPagesNoCacheMiddleware` 给的是 `private, no-cache`
    （可以存、每次回源校验）。但这些页面上过的是一次性验证码、密码和登录态，
    要的是 `no-store`（根本别落盘）。Django 自带的 LoginView 本身带
    never_cache，我们自己写的那几个视图得自己加 —— 漏一个不会有任何报错。
    """

    def test_every_account_entry_point_is_no_store(self):
        names = [
            "accounts:register", "accounts:register_new", "accounts:register_returning",
            "accounts:login", "accounts:code_login", "accounts:forgot_password",
        ]
        for name in names:
            with self.subTest(url=name):
                resp = self.client.get(reverse(name))
                cache_control = resp.headers.get("Cache-Control", "")
                self.assertIn("no-store", cache_control)
                self.assertIn("private", cache_control)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegisterFormMarkupTests(TestCase):
    """注册表单的渐进增强契约。

    分步、条件字段、验证码消息位这三样都是「坏了不报错」的东西，所以钉在测试里。
    """

    def setUp(self):
        self.body = self.client.get(reverse("accounts:register_new")).content.decode()

    def test_form_is_split_into_three_steps(self):
        # 属性名是 form-enhance.js 的通用契约，招新报名表用同一套
        self.assertIn("data-stepped-form", self.body)
        self.assertEqual(self.body.count("data-step>"), 3)
        self.assertIn("data-step-prev", self.body)
        self.assertIn("data-step-next", self.body)
        self.assertIn("data-step-submit", self.body)

    def test_no_novalidate_in_html(self):
        """没有 JS 时三段全部展开，原生校验可用且有用。

        novalidate 由 form-enhance.js 在接管之后自己打开 —— 那时字段会被藏起来，
        原生校验反而会报「An invalid form control is not focusable」（有报错、
        界面上没提示）。写在 HTML 里就等于把无 JS 用户的校验也一起关掉了。
        """
        self.assertNotIn("novalidate", self.body)

    def test_custom_specialty_field_is_conditional(self):
        """「自定义方向」只在选了「自定义」时才需要，但默认必须是可见的。"""
        self.assertIn('data-show-when="id_specialty=custom"', self.body)
        self.assertNotIn('data-show-when="id_specialty=custom" hidden', self.body)

    def test_code_field_has_a_message_slot(self):
        """验证码字段必须带消息位。

        原来注册页漏了它，于是「该邮箱已注册」「请求过于频繁」这些服务端提示
        在注册页一个都看不见 —— 用户只看到按钮闪一下就恢复，毫无头绪。
        `data-code-msg` 是 auth-code.js 找消息位的钩子。
        """
        self.assertIn("data-code-msg", self.body)
        self.assertIn('data-send-code="register"', self.body)

    def test_returning_channel_asks_for_the_original_role(self):
        body = self.client.get(reverse("accounts:register_returning")).content.decode()
        self.assertIn('name="requested_role"', body)
        self.assertNotIn('name="requested_role"', self.body)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegisterDoneTests(TestCase):
    """注册完成页：两条路都必须给出下一步，没有死胡同。"""

    def _payload(self, **over):
        data = {
            "username": "doneguy", "real_name": "小红", "student_id": "2025010188",
            "college": "信息与通信工程学院", "grade": "2025",
            "email": "done@example.com", "phone": "13800000088", "qq": "",
            "specialty": User.Specialty.HARDWARE, "specialty_custom": "",
            "privacy_consent": "on",
            "password1": "Str0ngPass!2025", "password2": "Str0ngPass!2025",
        }
        data.update(over)
        return data

    def test_new_member_without_an_open_campaign_gets_the_done_page(self):
        """没有开放批次时不能把新注册的人丢到「招新通道暂时关闭」上。

        那是个死胡同：他刚刚为了报名注册完账号，结果落在一句「关闭了」上面。
        """
        from recruitment.models import Campaign

        Campaign.objects.update(is_active=False)
        code = verification.issue("done@example.com", "register").code
        resp = self.client.post(reverse("accounts:register_new"), self._payload(code=code))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "accounts/register_done.html")
        self.assertEqual(resp.context["channel"], "new")
        # 账号照样是可用的招新成员，别让人以为注册失败了
        user = User.objects.get(username="doneguy")
        self.assertTrue(user.is_active)
        self.assertEqual(user.member_level, roles.LEVEL_APPLICANT)
        # 必须有下一步可点
        self.assertContains(resp, reverse("core:recruit"))

    def test_returning_member_done_page_explains_the_wait(self):
        code = verification.issue("done@example.com", "register").code
        resp = self.client.post(reverse("accounts:register_returning"), self._payload(
            code=code, requested_role=ReturningMembershipRequest.RequestedRole.MEMBER,
        ))
        self.assertTemplateUsed(resp, "accounts/register_done.html")
        self.assertEqual(resp.context["channel"], "returning")
        self.assertContains(resp, "待审核")
        self.assertContains(resp, reverse("accounts:login"))


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class VerificationTests(TestCase):
    def test_issue_sends_email(self):
        verification.issue("v@example.com", "register")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("验证码", mail.outbox[0].subject)

    def test_cooldown(self):
        verification.issue("v@example.com", "register")
        ok, _ = verification.can_send("v@example.com")
        self.assertFalse(ok)

    def test_verify_wrong_then_right(self):
        code = verification.issue("v@example.com", "login").code
        with self.assertRaises(verification.CodeError):
            verification.verify("v@example.com", "login", "000000")
        verification.verify("v@example.com", "login", code)  # 不抛异常即通过

    def test_forgot_password_resets(self):
        user = User.objects.create_user(username="bob", password="OldPass!2025", email="bob@example.com", is_active=True)
        user.member_level = roles.LEVEL_FORMAL
        user.save()
        code = verification.issue("bob@example.com", "reset").code
        resp = self.client.post(reverse("accounts:forgot_password"), {
            "email": "bob@example.com", "code": code,
            "new_password1": "BrandNew!2025", "new_password2": "BrandNew!2025",
        })
        self.assertEqual(resp.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.check_password("BrandNew!2025"))


class LevelTests(TestCase):
    def test_set_level_syncs_group_and_log(self):
        u = User.objects.create_user(username="c", password="x")
        u.set_level(roles.LEVEL_OFFICER, note="test")
        self.assertTrue(u.is_active)
        self.assertTrue(u.groups.filter(name="站务管理").exists())
        self.assertTrue(u.is_officer)
        self.assertEqual(u.level_logs.count(), 1)

    def test_promote_removes_old_group(self):
        u = User.objects.create_user(username="d", password="x")
        u.set_level(roles.LEVEL_APPLICANT)
        self.assertTrue(u.groups.filter(name="招新成员").exists())
        u.set_level(roles.LEVEL_FORMAL)
        self.assertFalse(u.groups.filter(name="招新成员").exists())
        self.assertTrue(u.groups.filter(name="科协会员").exists())

    def test_cohort_label(self):
        u = User.objects.create_user(username="e", password="x", grade="2025")
        self.assertEqual(u.cohort_label, "25届")

    def test_admin_level_sets_staff(self):
        u = User.objects.create_user(username="f", password="x")
        u.set_level(roles.LEVEL_ADMIN)
        u.refresh_from_db()
        self.assertTrue(u.is_staff)


@override_settings(NODEBB_JWT_SECRET=SSO_SECRET)
class SsoTests(TestCase):
    def test_sso_cookie_carries_level_and_position(self):
        import jwt

        pos = Position.objects.get(name="硬件主席")
        User.objects.create_user(username="ssou", password="Str0ngPass!2025", email="s@x.cn")
        user = User.objects.get(username="ssou")
        user.member_level = roles.LEVEL_FORMAL
        user.position = pos
        user.save()
        roles.sync_user_groups(user)

        self.client.login(username="ssou", password="Str0ngPass!2025")
        resp = self.client.get(reverse("core:home"))
        cookie = resp.cookies.get("heuesta_sso")
        self.assertIsNotNone(cookie)
        payload = jwt.decode(cookie.value, SSO_SECRET, algorithms=["HS256"])
        self.assertIn("科协会员", payload["groups"])
        self.assertIn("硬件主席", payload["groups"])

    def test_recruit_member_gets_no_forum_cookie(self):
        user = User.objects.create_user(username="recruit", password="Str0ngPass!2025")
        user.set_level(roles.LEVEL_APPLICANT)
        self.client.login(username="recruit", password="Str0ngPass!2025")
        resp = self.client.get(reverse("core:home"))
        self.assertIsNone(resp.cookies.get("heuesta_sso"))


class MedalTests(TestCase):
    def test_award_medal_unique(self):
        u = User.objects.create_user(username="g", password="x")
        m = Medal.objects.create(name="电赛国奖")
        UserMedal.objects.create(user=u, medal=m)
        self.assertEqual(u.medals.count(), 1)


# ---------------------------------------------------------------- 公开团队页

def make_team_member(username, position, *, show=True, **extra):
    """建一个「在任 + 已同意公开」的成员。默认已勾选，测不公开的那条自己传 show=False。"""
    defaults = {
        "member_level": roles.LEVEL_FORMAL,
        "is_active": True,
        "show_on_team": show,
        "position": position,
    }
    defaults.update(extra)
    user = User.objects.create_user(username=username, password="x")
    for key, value in defaults.items():
        setattr(user, key, value)
    user.save()
    return user


class TeamQuerysetTests(TestCase):
    """`User.team()` 是「谁上墙」的唯一口径，三个条件缺一不可。"""

    def setUp(self):
        self.chair = Position.objects.get(name="主席")
        self.hw = Position.objects.get(name="硬件主席")

    def test_opted_in_position_holder_is_on_the_wall(self):
        user = make_team_member("t1", self.chair, real_name="张三")
        self.assertIn(user, User.team())

    def test_not_opted_in_is_excluded(self):
        user = make_team_member("t2", self.chair, show=False)
        self.assertNotIn(user, User.team())

    def test_position_holder_who_is_inactive_is_excluded(self):
        user = make_team_member("t3", self.chair, is_active=False)
        self.assertNotIn(user, User.team())

    def test_member_without_position_is_excluded(self):
        """墙上是「现任团队」，不是会员名册 —— 没有职位就不在这一页上。"""
        user = make_team_member("t4", None)
        self.assertNotIn(user, User.team())

    def test_losing_the_position_removes_from_wall_without_touching_consent(self):
        user = make_team_member("t5", self.chair)
        user.position = None
        user.save(update_fields=["position"])
        self.assertNotIn(user, User.team())
        user.refresh_from_db()
        self.assertTrue(user.show_on_team, "解除职位不该顺手改掉本人的同意状态")

    def test_ordered_by_position_sort_order(self):
        """主席 sort_order=10 排在硬件主席 20 前面。按含金量排，不按注册顺序。"""
        hw = make_team_member("t6", self.hw)
        chair = make_team_member("t7", self.chair)
        self.assertEqual(list(User.team()), [chair, hw])

    def test_initial_plate_falls_back_for_blank_names(self):
        user = make_team_member("t8", self.chair, real_name="")
        self.assertEqual(user.initial, "T")
        named = make_team_member("t9", self.chair, real_name="李四")
        self.assertEqual(named.initial, "李")


class TeamSummaryTests(TestCase):
    """聚合数字必须是数出来的，而且「只有 1 个」时不显示。"""

    def test_counts_active_members_from_preparatory_up(self):
        chair = Position.objects.get(name="主席")
        make_team_member("s1", chair, college="集成电路学院", grade="2025")
        make_team_member("s2", None, college="计算机科学与技术学院", grade="2024",
                         member_level=roles.LEVEL_PREPARATORY)
        # 招新成员不算在册
        make_team_member("s3", None, college="数学科学学院", grade="2026",
                         member_level=roles.LEVEL_APPLICANT)
        # 未激活不算
        make_team_member("s4", None, college="航空航天学院", grade="2023", is_active=False)

        summary = User.team_summary()
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["colleges"], 2)
        self.assertEqual(summary["cohorts"], 2)

    def test_single_college_is_not_worth_saying(self):
        """「覆盖 1 个学院」不如不说 —— 返回 0 让模板整句不渲染。"""
        make_team_member("s5", None, college="集成电路学院", grade="2025")
        summary = User.team_summary()
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["colleges"], 0)
        self.assertEqual(summary["cohorts"], 0)

    def test_blank_college_is_not_counted_as_a_college(self):
        make_team_member("s6", None, college="集成电路学院", grade="2025")
        make_team_member("s7", None, college="", grade="")
        summary = User.team_summary()
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["colleges"], 0)


class TeamWallViewTests(TestCase):
    def setUp(self):
        self.chair = Position.objects.get(name="主席")
        self.hw = Position.objects.get(name="硬件主席")

    def test_wall_lists_opted_in_holders_with_their_position_on_the_card(self):
        """职位是卡片上的一枚徽章，不是分节标题 —— 协会的职位大多一人一个，
        按职位分节的话几个人就变成几个只装一张卡的分节，整页又空又长。"""
        make_team_member("w1", self.chair, real_name="陈主席", public_bio="统筹整体方向")
        make_team_member("w2", self.hw, real_name="王硬件")
        resp = self.client.get(reverse("team:wall"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("陈主席", body)
        self.assertIn("王硬件", body)
        self.assertIn("统筹整体方向", body)
        self.assertEqual(body.count('class="tm-card"'), 2)
        self.assertEqual(body.count('class="tm-pos"'), 2)

    def test_card_falls_back_to_the_position_blurb_when_no_bio(self):
        """本人没写介绍时退回职位的「这个职位做什么」，卡片不会只剩一个名字。"""
        self.hw.blurb = "带硬件方向的周常培训"
        self.hw.save(update_fields=["blurb"])
        make_team_member("w9", self.hw, real_name="王硬件")
        body = self.client.get(reverse("team:wall")).content.decode()
        self.assertIn("带硬件方向的周常培训", body)
        self.assertIn("tm-bio-role", body)

    def test_hero_does_not_promise_people_when_the_wall_is_empty(self):
        """Hero 结尾那句必须跟着有没有人变，否则它在指着一个空区块说「下面这些人」。"""
        make_team_member("w10", None, college="集成电路学院", grade="2025")
        body = self.client.get(reverse("team:wall")).content.decode()
        self.assertNotIn("下面这些", body)

        make_team_member("w11", self.chair, real_name="陈主席")
        body = self.client.get(reverse("team:wall")).content.decode()
        self.assertIn("下面这些", body)

    def test_wall_never_leaks_contact_details(self):
        """这一页的隐私边界：姓名可以（本人同意过），联系方式和学号一律不出现。

        隐私说明里写的是「公开页面不会展示手机号、邮箱或完整学号」，而这一页是
        全站唯一一个把成员逐个列出来的公开页面 —— 泄漏在这里最可能发生，而且
        页面照常渲染、没有任何报错。

        性别与出生日期也在这里守：它们是招新报名表带进来的档案，隐私说明写的是
        「报名答卷、性别与出生日期不出现在任何公开页面上」。**`User` 上每加一个
        字段，这一条就要跟着加一个探针** —— 卡片模板改一行就可能把它渲染出来。
        """
        make_team_member(
            "w3", self.chair, real_name="李隐私",
            phone="13800001234", email="leak@example.cn",
            student_id="2025999888", qq="998877665",
            gender=User.Gender.FEMALE, birthday=date(2005, 12, 31),
        )
        body = self.client.get(reverse("team:wall")).content.decode()
        self.assertIn("李隐私", body)
        for secret in ("13800001234", "leak@example.cn", "2025999888", "998877665"):
            self.assertNotIn(secret, body, f"团队页泄漏了 {secret}")
        # 日期要搜**多种渲染**，不能只搜一种：`{{ u.birthday }}` 在 zh-hans 下是
        # 「2005年12月31日」、`|date:"Y-m-d"` 是「2005-12-31」、`|date:"Y"` 只剩
        # 「2005」。单搜年份能一网打尽，另外几条是为了让失败信息说得清是哪种写法。
        # （测试用的是明文静态路径，没有十六进制哈希，所以搜「2005」不会误命中。）
        for probe in ("2005", "2005-12-31", "2005年12月31日", "12月31日"):
            self.assertNotIn(probe, body, f"团队页泄漏了出生日期（{probe}）")
        # 性别存的是 "female"，渲染出来是「女」—— 两个都要搜。
        # 已确认 base.html / includes / team_wall.html 里没有「女」字，不会误报。
        for probe in ("female", "女"):
            self.assertNotIn(probe, body, f"团队页泄漏了性别（{probe}）")

    def test_member_without_avatar_gets_an_initial_plate_not_a_broken_image(self):
        make_team_member("w4", self.chair, real_name="赵无头像")
        body = self.client.get(reverse("team:wall")).content.decode()
        self.assertIn('class="tm-initial"', body)
        self.assertNotIn('class="tm-avatar"', body)

    def test_empty_wall_explains_why_and_gives_a_next_step(self):
        """一个人都没勾时不能是白板：说清原因，并给出「现在怎么找人」。"""
        body = self.client.get(reverse("team:wall")).content.decode()
        self.assertIn("empty-state", body)
        self.assertNotIn('class="tm-group"', body)
        self.assertIn(reverse("core:recruit"), body)

    def test_summary_line_survives_an_empty_wall(self):
        """墙是空的，但在册人数照常显示 —— 这是这一页在零 opt-in 时的全部内容。"""
        make_team_member("w5", None, college="集成电路学院", grade="2025")
        make_team_member("w6", None, college="计算机科学与技术学院", grade="2024")
        body = self.client.get(reverse("team:wall")).content.decode()
        self.assertIn("empty-state", body)
        self.assertIn("在册", body)
        self.assertIn(">2<", body)

    def test_officer_sees_the_optin_reminder_and_visitors_do_not(self):
        make_team_member("w7", self.chair, show=False)
        body = self.client.get(reverse("team:wall")).content.decode()
        self.assertNotIn("tm-officer-note", body)

        officer = User.objects.create_user(username="w8", password="x")
        officer.set_level(roles.LEVEL_OFFICER)
        self.client.login(username="w8", password="x")
        body = self.client.get(reverse("team:wall")).content.decode()
        self.assertIn("tm-officer-note", body)
        self.assertIn(reverse("dashboard:positions"), body)

    def test_wall_is_reachable_without_login(self):
        """公开页面。挂在 accounts 里但不在 /accounts/ 下，就是为了不被账号门槛拦住。"""
        self.assertEqual(self.client.get("/team/").status_code, 200)


class ProfileTeamOptInTests(TestCase):
    """公开展示是本人的同意，入口只有一个：自己的个人资料页。"""

    def setUp(self):
        self.chair = Position.objects.get(name="主席")

    def _login(self, user):
        user.set_password("Str0ngPass!2025")
        user.save()
        self.client.login(username=user.username, password="Str0ngPass!2025")

    def test_optin_fields_hidden_for_members_without_a_position(self):
        """没有职位的人不会上墙，给他一个勾了也没反应的开关等于坏界面。"""
        user = make_team_member("p1", None, show=False)
        self._login(user)
        body = self.client.get(reverse("accounts:profile_edit")).content.decode()
        self.assertNotIn("show_on_team", body)
        self.assertNotIn("pf-team", body)

    def test_optin_fields_appear_for_position_holders(self):
        user = make_team_member("p2", self.chair, show=False)
        self._login(user)
        body = self.client.get(reverse("accounts:profile_edit")).content.decode()
        self.assertIn("show_on_team", body)
        self.assertIn("public_bio", body)

    def test_member_can_opt_in_and_out(self):
        user = make_team_member("p3", self.chair, show=False, real_name="孙同意",
                                college="集成电路学院", grade="2025")
        self._login(user)
        payload = {
            "real_name": "孙同意", "college": "集成电路学院", "grade": "2025",
            "specialty": "hardware", "specialty_custom": "", "qq": "", "phone": "",
            "show_on_team": "on", "public_bio": "负责硬件培训",
        }
        self.client.post(reverse("accounts:profile_edit"), payload)
        user.refresh_from_db()
        self.assertTrue(user.show_on_team)
        self.assertEqual(user.public_bio, "负责硬件培训")

        payload.pop("show_on_team")
        self.client.post(reverse("accounts:profile_edit"), payload)
        user.refresh_from_db()
        self.assertFalse(user.show_on_team)

    def test_a_member_without_a_position_cannot_smuggle_the_flag_through_the_form(self):
        """字段被摘掉之后，POST 里带上它也没有用 —— 否则「只对有职位的人显示」
        就只是界面上的装饰，任何人 curl 一下都能把自己标成已同意。"""
        user = make_team_member("p4", None, show=False, real_name="周越权",
                                college="集成电路学院", grade="2025")
        self._login(user)
        self.client.post(reverse("accounts:profile_edit"), {
            "real_name": "周越权", "college": "集成电路学院", "grade": "2025",
            "specialty": "hardware", "specialty_custom": "", "qq": "", "phone": "",
            "show_on_team": "on", "public_bio": "偷偷加的",
        })
        user.refresh_from_db()
        self.assertFalse(user.show_on_team)
        self.assertEqual(user.public_bio, "")


class ProfileApplicantFieldsTests(TestCase):
    """性别与出生日期：招新报名表带进来的两项档案，本人在这一页能改。"""

    def _login(self, user):
        user.set_password("Str0ngPass!2025")
        user.save()
        self.client.login(username=user.username, password="Str0ngPass!2025")

    def _payload(self, **over):
        data = {
            "real_name": "钱档案", "college": "集成电路学院", "grade": "2025",
            "specialty": "hardware", "specialty_custom": "", "qq": "", "phone": "",
            "gender": "", "birthday": "",
        }
        data.update(over)
        return data

    def _user(self):
        user = make_team_member("pa1", None, show=False, real_name="钱档案",
                                college="集成电路学院", grade="2025")
        self._login(user)
        return user

    def test_member_can_fill_and_change_them(self):
        user = self._user()
        self.client.post(reverse("accounts:profile_edit"),
                         self._payload(gender="female", birthday="2005-12-31"))
        user.refresh_from_db()
        self.assertEqual(user.gender, "female")
        self.assertEqual(user.birthday, date(2005, 12, 31))

    def test_both_are_optional_and_blank_means_not_disclosed(self):
        """性别留空就是「不愿透露」—— 不另设一个枚举值，两种表达同一件事迟早
        有一处判断只查其中一种。出生日期留空也必须能存（null=True）。"""
        user = self._user()
        resp = self.client.post(reverse("accounts:profile_edit"), self._payload())
        self.assertEqual(resp.status_code, 302, "两项都留空应当能保存")
        user.refresh_from_db()
        self.assertEqual(user.gender, "")
        self.assertIsNone(user.birthday)

    def test_saved_birthday_is_rendered_back_in_the_format_the_input_expects(self):
        """**这一条守的是一个静默故障。**

        `<input type="date">` 只认 ISO 的 `YYYY-MM-DD`。不给 widget 指定
        `format` 时，已存的值会按 Django 的本地化格式渲染（zh-hans 下是
        「2005年12月31日」），浏览器读不懂就**显示成一个空框** —— 于是用户每次
        打开资料页保存一次，就顺手把自己的生日清掉了，而页面一切正常、没有任何
        报错。所以这里断言的是「渲染出来的 value 长什么样」，不是「存进去了没有」。
        """
        user = self._user()
        user.birthday = date(2005, 12, 31)
        user.gender = "male"
        user.save(update_fields=["birthday", "gender"])

        body = self.client.get(reverse("accounts:profile_edit")).content.decode()
        self.assertIn('value="2005-12-31"', body,
                      "日期没有按 ISO 回填，浏览器会把它显示成空框")
        self.assertNotIn("2005年12月31日", body)
        # 顺带确认往返一圈不会丢：把渲染出来的值原样提交回去，日期应当不变
        self.client.post(reverse("accounts:profile_edit"),
                         self._payload(gender="male", birthday="2005-12-31"))
        user.refresh_from_db()
        self.assertEqual(user.birthday, date(2005, 12, 31))

    def test_the_empty_choice_reads_as_a_real_answer_not_a_placeholder(self):
        """空选项的标签是「不愿透露」而不是 Django 默认的「---------」：
        不填是一个正当的答案，不是「还没选」。"""
        self._user()
        body = self.client.get(reverse("accounts:profile_edit")).content.decode()
        self.assertIn("不愿透露", body)
