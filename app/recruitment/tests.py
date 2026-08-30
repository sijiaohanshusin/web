from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import roles

from .models import Application, Campaign

User = get_user_model()


def make_campaign(**kw):
    now = timezone.now()
    defaults = {
        "name": "2026 秋季招新",
        "intro": "欢迎加入！",
        "opens_at": now - timedelta(days=1),
        "closes_at": now + timedelta(days=7),
        "is_active": True,
    }
    defaults.update(kw)
    return Campaign.objects.create(**defaults)


def make_user(name="stu", level=roles.LEVEL_APPLICANT):
    u = User.objects.create_user(username=name, password="Str0ngPass!2025", is_active=True)
    u.set_level(level)
    return u


def apply_payload(**over):
    """一份合法的报名 POST 体（含 ApplicantProfileForm 那两项）。

    **集中一处**：报名表的必填项会随纸质表口径变，散在各处的 POST 字典每加一个
    必填项就要挨个去改 —— 漏一个的表现是那条测试莫名开始 assert「表单不合法」，
    而它测的压根是别的东西。
    """
    data = {
        "department": "hardware",
        "interests": ["mcu"],
        "interests_other": "",
        "skills": "会一点 C",
        "self_intro": "我是新生，非常想加入硬件部学习焊接。",
        "first_impression": "",
        "motto": "",
        "heard_from": ["senior"],
        "heard_from_other": "",
        # ApplicantProfileForm（写 User，同一次 POST）
        "gender": "",
        "birthday": "",
    }
    data.update(over)
    return data


class CampaignModelTests(TestCase):
    def test_is_open_window(self):
        now = timezone.now()
        self.assertTrue(make_campaign().is_open)
        self.assertFalse(make_campaign(opens_at=now + timedelta(days=1)).is_open)
        self.assertFalse(make_campaign(closes_at=now - timedelta(days=1)).is_open)
        self.assertFalse(make_campaign(is_active=False).is_open)

    def test_open_ended_campaign(self):
        self.assertTrue(make_campaign(closes_at=None).is_open)


class ApplyFlowTests(TestCase):
    def setUp(self):
        Campaign.objects.update(is_active=False)
        self.campaign = make_campaign()
        self.user = make_user()
        self.client.login(username="stu", password="Str0ngPass!2025")

    def test_index_shows_form_for_applicant(self):
        resp = self.client.get(reverse("recruitment:index"))
        self.assertContains(resp, "报名表")
        self.assertIn("no-cache", resp.headers["Cache-Control"])

    def test_apply_creates_application(self):
        resp = self.client.post(reverse("recruitment:apply"), apply_payload())
        self.assertEqual(resp.status_code, 302)
        app = Application.objects.get(user=self.user, campaign=self.campaign)
        self.assertEqual(app.status, Application.Status.SUBMITTED)
        self.assertEqual(app.department, "hardware")

    def test_short_intro_rejected(self):
        resp = self.client.post(reverse("recruitment:apply"),
                                apply_payload(department="software", self_intro="太短"))
        self.assertFalse(Application.objects.filter(user=self.user).exists())
        self.assertContains(resp, "自我介绍太短")

    def test_duplicate_apply_blocked(self):
        Application.objects.create(campaign=self.campaign, user=self.user, self_intro="第一次报名的自我介绍内容")
        self.client.post(reverse("recruitment:apply"),
                         apply_payload(self_intro="重复报名应当被拦截掉的内容"))
        self.assertEqual(Application.objects.filter(user=self.user).count(), 1)

    def test_pending_user_promoted_to_applicant_on_apply(self):
        pending = User.objects.create_user(username="p0", password="Str0ngPass!2025", is_active=True)
        pending.set_level(roles.LEVEL_PENDING)
        self.client.login(username="p0", password="Str0ngPass!2025")
        self.client.post(reverse("recruitment:apply"),
                         apply_payload(department="undecided", skills="",
                                       self_intro="零基础但很想学，请给我机会。"))
        pending.refresh_from_db()
        self.assertEqual(pending.member_level, roles.LEVEL_APPLICANT)

    def test_formal_member_cannot_apply(self):
        formal = make_user("formal", roles.LEVEL_FORMAL)
        self.client.login(username="formal", password="Str0ngPass!2025")
        resp = self.client.post(reverse("recruitment:apply"),
                                apply_payload(self_intro="我已经是科协会员了还来报名。"),
                                follow=True)
        self.assertFalse(Application.objects.filter(user=formal).exists())
        self.assertContains(resp, "已经是科协会员")


class RecruitDashboardTests(TestCase):
    def setUp(self):
        Campaign.objects.update(is_active=False)
        self.campaign = make_campaign()
        self.officer = make_user("off", roles.LEVEL_OFFICER)
        self.applicant = make_user("newbie", roles.LEVEL_APPLICANT)
        self.app = Application.objects.create(
            campaign=self.campaign, user=self.applicant, self_intro="想加入的自我介绍内容足够长。",
        )
        self.client.login(username="off", password="Str0ngPass!2025")

    def test_member_cannot_access(self):
        make_user("plain")
        self.client.login(username="plain", password="Str0ngPass!2025")
        resp = self.client.get(reverse("dashboard:recruitment"))
        self.assertEqual(resp.status_code, 403)

    def test_first_pass_promotes_to_preparatory(self):
        self.client.post(reverse("dashboard:recruitment"), {
            "action": "set_result", "result": "first_pass", "ids": [self.app.pk],
            "note": "表现不错",
        })
        self.app.refresh_from_db()
        self.applicant.refresh_from_db()
        self.assertEqual(self.app.status, Application.Status.FIRST_PASS)
        self.assertEqual(self.app.interview_note, "表现不错")
        self.assertEqual(self.applicant.member_level, roles.LEVEL_PREPARATORY)

    def test_second_pass_promotes_to_formal(self):
        self.client.post(reverse("dashboard:recruitment"), {
            "action": "set_result", "result": "second_pass", "ids": [self.app.pk],
        })
        self.applicant.refresh_from_db()
        self.assertEqual(self.applicant.member_level, roles.LEVEL_FORMAL)

    def test_reject_notifies_and_no_promotion(self):
        self.client.post(reverse("dashboard:recruitment"), {
            "action": "set_result", "result": "reject", "ids": [self.app.pk],
        })
        self.app.refresh_from_db()
        self.applicant.refresh_from_db()
        self.assertEqual(self.app.status, Application.Status.REJECTED)
        self.assertEqual(self.applicant.member_level, roles.LEVEL_APPLICANT)
        self.assertEqual(self.applicant.notifications.filter(title__contains="招新结果").count(), 1)

    def test_csv_export(self):
        resp = self.client.get(reverse("dashboard:recruitment"), {"campaign": self.campaign.pk, "export": "csv"})
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8-sig")
        self.assertIn("newbie", resp.content.decode("utf-8-sig"))

    def test_campaign_create(self):
        start = timezone.now()
        resp = self.client.post(reverse("dashboard:campaign_create"), {
            "name": "2027 春季招新",
            "intro": "## 招新\n\n春季补录",
            "opens_at": start.strftime("%Y-%m-%dT%H:%M"),
            "closes_at": (start + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M"),
            "is_active": "on",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Campaign.objects.filter(name="2027 春季招新").exists())


class CampaignCurrentTests(TestCase):
    """Campaign.current() —— 对外展示用的「当前批次」。

    这个答案有三个消费者：报名页、导航条的招新入口、首页 CTA 的倒计时。逻辑放在
    模型上就是为了让三处永远一致，否则迟早出现「导航说在招新、首页说已截止」。
    """

    def setUp(self):
        Campaign.objects.update(is_active=False)
        self.now = timezone.now()

    def test_prefers_an_open_campaign_over_a_newer_closed_one(self):
        """开放中的优先，即使有更新的批次已经截止。"""
        open_one = Campaign.objects.create(
            name="进行中", is_active=True,
            opens_at=self.now - timedelta(days=10),
            closes_at=self.now + timedelta(days=5),
        )
        Campaign.objects.create(
            name="更新但已截止", is_active=True,
            opens_at=self.now - timedelta(days=1),
            closes_at=self.now - timedelta(hours=1),
        )
        self.assertEqual(Campaign.current(), open_one)

    def test_falls_back_to_the_latest_active_when_none_is_open(self):
        """全都不在窗口内时给最近的那个 —— 报名页要有东西可展示。"""
        Campaign.objects.create(
            name="旧的", is_active=True,
            opens_at=self.now - timedelta(days=100),
            closes_at=self.now - timedelta(days=90),
        )
        newest = Campaign.objects.create(
            name="最近的", is_active=True,
            opens_at=self.now - timedelta(days=2),
            closes_at=self.now - timedelta(days=1),
        )
        self.assertEqual(Campaign.current(), newest)

    def test_ignores_disabled_campaigns(self):
        Campaign.objects.create(
            name="停用的", is_active=False,
            opens_at=self.now - timedelta(days=1),
            closes_at=self.now + timedelta(days=5),
        )
        self.assertIsNone(Campaign.current())

    def test_none_when_there_are_no_campaigns_at_all(self):
        Campaign.objects.all().delete()
        self.assertIsNone(Campaign.current())


class ApplicationProgressTests(TestCase):
    """报名进度的模型侧语义。

    页面的时间线直接读这两个属性，所以「走到第几步」的判断只有一处实现。
    """

    def setUp(self):
        Campaign.objects.update(is_active=False)
        self.campaign = Campaign.objects.create(
            name="批次", is_active=True,
            opens_at=timezone.now() - timedelta(days=1),
            closes_at=timezone.now() + timedelta(days=5),
        )
        self.user = User.objects.create_user(username="applicant2", password="x")
        self.user.set_level(roles.LEVEL_APPLICANT)

    def _app(self, status):
        return Application.objects.create(
            campaign=self.campaign, user=self.user,
            self_intro="够长的自我介绍内容。", status=status,
        )

    def test_reached_index_follows_the_three_steps(self):
        cases = {
            Application.Status.SUBMITTED: 0,
            Application.Status.FIRST_PASS: 1,
            Application.Status.SECOND_PASS: 2,
        }
        for status, expected in cases.items():
            with self.subTest(status=status):
                app = self._app(status)
                self.assertEqual(app.reached_index, expected)
                app.delete()

    def test_rejected_is_a_terminal_state_not_a_fourth_step(self):
        """未录取不进时间线：它是任何一步都可能走到的终止态，不是「最后一个成就」。"""
        app = self._app(Application.Status.REJECTED)
        self.assertTrue(app.is_rejected)
        # 只能确定「报名」这一步成立 —— 数据库不保留「之前通过到哪一面」
        self.assertEqual(app.reached_index, 0)
        self.assertEqual(len(Application.PROGRESS_STEPS), 3)
        keys = [k for k, _, _ in Application.PROGRESS_STEPS]
        self.assertNotIn(Application.Status.REJECTED, keys)


class ApplyWritesTwoModelsTests(TestCase):
    """一次 POST 写两个模型：答卷进 `Application`，性别与出生日期进 `User`。"""

    def setUp(self):
        Campaign.objects.update(is_active=False)
        self.campaign = make_campaign()
        self.user = make_user()
        self.client.login(username="stu", password="Str0ngPass!2025")

    def _post(self, **over):
        return self.client.post(reverse("recruitment:apply"), apply_payload(**over))

    def test_a_full_answer_sheet_lands_in_both_models(self):
        resp = self._post(
            interests=["mcu", "dsp_fpga", "other"], interests_other="电机控制",
            first_impression="在实验室门口看到过一墙作品。",
            motto="想做出一台自己的示波器。",
            heard_from=["senior", "online"],
            gender="female", birthday="2007-11-23",
        )
        self.assertEqual(resp.status_code, 302)

        app = Application.objects.get(user=self.user, campaign=self.campaign)
        self.assertEqual(app.interests, ["mcu", "dsp_fpga", "other"])
        self.assertEqual(app.interests_other, "电机控制")
        self.assertEqual(app.heard_from, ["senior", "online"])
        self.assertEqual(app.first_impression, "在实验室门口看到过一墙作品。")
        self.assertEqual(app.motto, "想做出一台自己的示波器。")

        self.user.refresh_from_db()
        self.assertEqual(self.user.gender, "female")
        self.assertEqual(self.user.birthday, date(2007, 11, 23))

    def test_the_two_multi_selects_are_required(self):
        """断言表单状态而不是页面文字：这两个字段渲染成什么样是模板的事，
        由 scripts/check_recruitment.py 在真浏览器里验。"""
        for field in ("interests", "heard_from"):
            with self.subTest(field=field):
                resp = self._post(**{field: []})
                self.assertFalse(Application.objects.filter(user=self.user).exists())
                self.assertIn("至少选一项", str(resp.context["form"].errors[field]))

    def test_nobody_gets_stuck_on_the_required_multi_selects(self):
        """两项都必填，但都留了出口：兴趣里有「目前还不了解」，渠道里有「其他」。
        只选出口项也必须能提交完 —— 否则「必填」就变成一道劝退的墙。"""
        resp = self._post(interests=["unknown"], heard_from=["other"], heard_from_other="路过看到的")
        self.assertEqual(resp.status_code, 302)
        app = Application.objects.get(user=self.user)
        self.assertEqual(app.interests, ["unknown"])
        self.assertEqual(app.channels_display, "其他：路过看到的")

    def test_picking_other_without_a_supplement_errors_on_the_supplement_field(self):
        """错误要挂在**补充字段**上 —— 那才是用户要动手的地方。挂在多选字段上的
        后果是提示出现在一排复选框下面，而光标该去的输入框旁边一片干净。"""
        resp = self._post(interests=["other"], interests_other="")
        self.assertFalse(Application.objects.filter(user=self.user).exists())
        form = resp.context["form"]
        self.assertIn("interests_other", form.errors)
        self.assertNotIn("interests", form.errors)

    def test_a_leftover_supplement_is_dropped_when_other_is_unchecked(self):
        """勾掉了「其他」却留着上次填的字，不该把它存进库 —— 那会在详情页上冒出
        一句没有归属的话。"""
        resp = self._post(interests=["mcu"], interests_other="上次填的残留")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Application.objects.get(user=self.user).interests_other, "")

    def test_both_forms_report_their_errors_in_one_go(self):
        """**这一条守的是 `and` 短路。**

        `form.is_valid() and profile_form.is_valid()` 会让第一张不合法时第二张
        压根不校验，于是它的错误一条都不显示 —— 用户改完第一处再提交，又冒出一批
        新错误，来回好几趟才知道到底有几个问题。所以断言的是「两张表的错误同时
        出现」，而不是「提交失败了」。
        """
        resp = self._post(self_intro="太短", birthday="不是日期")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Application.objects.filter(user=self.user).exists())
        self.assertTrue(resp.context["form"].errors, "答卷那张表该有错误")
        self.assertTrue(resp.context["profile_form"].errors, "档案那张表也该有错误")
        self.assertContains(resp, "自我介绍太短")

    def test_a_bad_profile_field_does_not_leave_a_half_written_record(self):
        """原子性：档案不合法时报名也不能落库，否则会留下「资料改了但没报上名」。"""
        self._post(birthday="2007-13-45")
        self.assertFalse(Application.objects.filter(user=self.user).exists())
        self.user.refresh_from_db()
        self.assertIsNone(self.user.birthday)

    def test_the_profile_pair_is_optional(self):
        resp = self._post(gender="", birthday="")
        self.assertEqual(resp.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.gender, "")
        self.assertIsNone(self.user.birthday)

    def test_the_failed_submission_still_carries_the_live_stats(self):
        """校验失败重渲染时 context 原来漏了 stats —— 模板有 {% if %} 兜着所以
        不报错，但统计块会走空态分支，页面上的「N 人已报名」凭空变没了。"""
        Application.objects.create(campaign=self.campaign, user=make_user("other1"),
                                   self_intro="别人先报了一个名。")
        resp = self._post(self_intro="太短")
        self.assertEqual(resp.context["stats"]["total"], 1)
        self.assertIn("progress_steps", resp.context)

    def test_the_form_is_prefilled_with_what_the_account_already_knows(self):
        """已经填过生日的人不该再填一遍 —— 报名表打开时就带着现有的值。

        这里只验表单绑到了账号（`instance=request.user`）。「渲染出来的 value 是不是
        ISO」那一条在 accounts 侧有专门的测试钉着（不是 ISO 的话浏览器显示空框，
        用户一保存就把生日清掉了）。
        """
        self.user.gender = "male"
        self.user.birthday = date(2006, 5, 4)
        self.user.save(update_fields=["gender", "birthday"])
        resp = self.client.get(reverse("recruitment:index"))
        profile_form = resp.context["profile_form"]
        self.assertEqual(profile_form.initial["birthday"], date(2006, 5, 4))
        self.assertEqual(profile_form.initial["gender"], "male")

    def test_anonymous_visitors_do_not_get_a_profile_form(self):
        self.client.logout()
        resp = self.client.get(reverse("recruitment:index"))
        self.assertIsNone(resp.context["profile_form"])


class MultiChoiceFieldTests(TestCase):
    """`interests` / `heard_from` 两个多选项。

    它们存在 `JSONField` 里，而 **`JSONField` 对内容零校验** —— 往里塞任何 JSON
    都能存进去，`clean()` 在 `save()` 时也压根不跑。所以这一批断言分三层守：
      1. `full_clean()` 挡非法键（表单与 admin 走这条）
      2. 显示时**静默跳过**认不出的键（挡已经进了库的脏数据，不炸页面）
      3. 统计按固定顺序返回全部选项，包括 0 次的
    """

    def setUp(self):
        self.campaign = make_campaign()

    def _app(self, name="mc", **kw):
        data = {
            "campaign": self.campaign, "user": make_user(name),
            "self_intro": "自我介绍够十个字了吧。",
        }
        data.update(kw)
        return Application.objects.create(**data)

    # ---- 第一层：full_clean 挡非法键 ----

    def test_valid_keys_pass_full_clean(self):
        app = self._app(
            interests=[Application.Interest.MCU, Application.Interest.POWER],
            heard_from=[Application.Channel.SENIOR],
        )
        app.full_clean()          # 不抛就算过

    def test_unknown_key_is_rejected_by_full_clean(self):
        app = self._app(interests=["mcu", "quantum_computing"])
        with self.assertRaises(ValidationError) as caught:
            app.full_clean()
        self.assertIn("interests", caught.exception.error_dict)
        self.assertIn("quantum_computing", str(caught.exception))

    def test_non_list_value_is_rejected(self):
        """`JSONField` 存字符串、字典都是合法 JSON，但语义上是坏数据。"""
        for i, bad in enumerate(("mcu", {"mcu": True}, 42)):
            with self.subTest(bad=bad):
                app = self._app(f"mcnotlist{i}", heard_from=bad)
                with self.assertRaises(ValidationError):
                    app.full_clean()

    def test_empty_is_allowed_at_the_model_layer(self):
        """模型层允许留空（数据迁移与 admin 要能建半成品）。
        「至少选一项」是**表单层**的要求，两层职责不同。"""
        app = self._app()
        app.full_clean()
        self.assertEqual(app.interests, [])
        self.assertEqual(app.heard_from, [])

    # ---- 第二层：显示时跳过认不出的键 ----

    def test_display_skips_keys_it_does_not_recognise(self):
        """选项以后会退役（纸质表上原来还有「人人网」），历史数据仍留着旧键。
        原样显示会冒出一个 `rr_net`，抛异常会让整页 500 —— 跳过是唯一不制造新
        问题的选择。**这一条不能用 full_clean 造数据**，只能直接塞。"""
        app = self._app(heard_from=["senior", "rr_net", "online"])
        self.assertEqual(app.channels_display, "高年级学长学姐介绍、海报 / 官网 / QQ / 公众号")

    def test_display_is_empty_for_blank_and_none(self):
        app = self._app("mcblank")
        self.assertEqual(app.interests_display, "")
        self.assertEqual(app.channels_display, "")
        # 老数据可能是 NULL 而不是 []
        app.interests = None
        self.assertEqual(app.interests_display, "")

    def test_other_carries_its_supplement_into_the_display(self):
        app = self._app(
            "mcother",
            interests=[Application.Interest.MCU, Application.Interest.OTHER],
            interests_other="电机控制",
        )
        self.assertEqual(app.interests_display, "单片机编程与设计、其他：电机控制")

    def test_other_without_a_supplement_still_reads_fine(self):
        """选了「其他」但没写补充时不能出现一个孤零零的冒号。"""
        app = self._app("mconly", interests=[Application.Interest.OTHER])
        self.assertEqual(app.interests_display, "其他")

    def test_display_follows_the_order_declared_in_the_data(self):
        """按用户勾选存下来的顺序渲染，不重排 —— 重排会让确认页回显和详情页不一致。"""
        app = self._app("mcorder", interests=["power", "mcu"])
        self.assertEqual(app.interests_display, "电源开发与设计、单片机编程与设计")

    # ---- 第三层：统计 ----

    def test_breakdown_counts_match_a_recount_and_keep_zero_rows(self):
        """拿现场重新数一遍的结果比，而不是比一个写死的数字。

        「一个人都没选电源方向」本身就是要看的信息，所以 0 次的行必须还在 ——
        只返回非零项会让那一行凭空消失、读者以为漏统计了。
        """
        picks = [
            ["mcu", "power"],
            ["mcu", "rf", "other"],
            ["unknown"],
            [],
        ]
        for i, keys in enumerate(picks):
            self._app(f"mcb{i}", interests=keys)

        apps = list(Application.objects.filter(campaign=self.campaign))
        got = dict(Application.interest_breakdown(apps))

        expected = {}
        for value, label in Application.Interest.choices:
            expected[label] = sum(1 for keys in picks if value in keys)
        self.assertEqual(got, expected)

        # 全部选项都在（含 0 次的），而且顺序跟着 choices
        rows = Application.interest_breakdown(apps)
        self.assertEqual(len(rows), len(Application.Interest.choices))
        self.assertEqual([label for label, _ in rows],
                         [label for _, label in Application.Interest.choices])
        self.assertEqual(dict(rows)["模型控制类"], 0)

    def test_breakdown_ignores_unknown_keys_without_crashing(self):
        self._app("mcbad", heard_from=["senior", "rr_net"])
        apps = list(Application.objects.filter(campaign=self.campaign))
        rows = dict(Application.channel_breakdown(apps))
        self.assertEqual(rows["高年级学长学姐介绍"], 1)
        self.assertNotIn("rr_net", rows)

    def test_breakdown_on_an_empty_queryset_still_lists_every_option(self):
        """一条报名都没有时不能返回空表 —— 那一块会整个不渲染，看着像坏了。"""
        rows = Application.channel_breakdown([])
        self.assertEqual(len(rows), len(Application.Channel.choices))
        self.assertEqual({n for _, n in rows}, {0})


class RecruitmentPageStateTests(TestCase):
    """招新落地页的状态分支与实时数据。

    渲染层面的完整验证（六种状态真的打开页面看）在 scripts/check_recruitment.py。
    这里守服务端算出来的东西：四态标志位、统计口径、以及「方向」必须是单选卡片。
    """

    def setUp(self):
        Campaign.objects.update(is_active=False)
        self.url = reverse("recruitment:index")
        self.campaign = Campaign.objects.create(
            name="2026 测试招新", is_active=True,
            opens_at=timezone.now() - timedelta(days=1),
            closes_at=timezone.now() + timedelta(days=7),
        )

    def _login(self, level):
        user = User.objects.create_user(username=f"u{level}", password="x")
        user.set_level(level)
        self.client.login(username=f"u{level}", password="x")
        return user

    def test_anonymous_gets_no_form(self):
        resp = self.client.get(self.url)
        self.assertFalse(resp.context["can_apply"])
        self.assertNotContains(resp, 'id="rec-form"')

    def test_applicant_can_apply(self):
        self._login(roles.LEVEL_APPLICANT)
        resp = self.client.get(self.url)
        self.assertTrue(resp.context["can_apply"])
        self.assertContains(resp, 'id="rec-form"')
        # 五段 fieldset —— 分步是前端的事，但段落划分在模板里。
        # 属性名是 form-enhance.js 的通用契约（注册表单也用同一套）。
        body = resp.content.decode()
        self.assertEqual(body.count("data-step>"), 5)
        self.assertIn("data-stepped-form", body)
        # 两张 ModelForm 在同一个 <form> 里：答卷进 Application，档案进 User。
        # 少渲染一个必填项的后果是**谁都交不上表**，而错误提示挂在一个看不见的
        # 字段上 —— 用户只看到点了提交没反应。
        for name in ("interests", "heard_from", "gender", "birthday"):
            self.assertIn(f'name="{name}"', body, f"{name} 没有渲染出来")
        # 步骤点数量与段数是否一致由 scripts/check_recruitment.py 用 DOM 查询验
        # （这里用字符串数 <li> 会把页面上别处的列表一起数进来）。

    def test_formal_member_gets_no_form(self):
        self._login(roles.LEVEL_FORMAL)
        resp = self.client.get(self.url)
        self.assertTrue(resp.context["already_member"])
        self.assertNotContains(resp, 'id="rec-form"')

    def test_existing_application_replaces_the_form_with_a_track(self):
        user = self._login(roles.LEVEL_APPLICANT)
        Application.objects.create(
            campaign=self.campaign, user=user, self_intro="够长的自我介绍内容。",
        )
        resp = self.client.get(self.url)
        self.assertNotContains(resp, 'id="rec-form"')
        self.assertContains(resp, "rec-track")

    def test_closed_campaign_gets_no_form(self):
        self._login(roles.LEVEL_APPLICANT)
        self.campaign.closes_at = timezone.now() - timedelta(hours=1)
        self.campaign.save(update_fields=["closes_at"])
        resp = self.client.get(self.url)
        self.assertFalse(resp.context["can_apply"])
        self.assertNotContains(resp, 'id="rec-form"')

    def test_no_active_campaign_at_all(self):
        Campaign.objects.update(is_active=False)
        resp = self.client.get(self.url)
        self.assertIsNone(resp.context["campaign"])
        self.assertContains(resp, "招新通道")

    def test_stats_count_by_department_in_one_query(self):
        u1 = User.objects.create_user(username="a1", password="x")
        u2 = User.objects.create_user(username="a2", password="x")
        for user, dept in ((u1, Application.Department.HARDWARE),
                           (u2, Application.Department.HARDWARE)):
            Application.objects.create(
                campaign=self.campaign, user=user, department=dept,
                self_intro="够长的自我介绍内容。",
            )
        resp = self.client.get(self.url)
        stats = resp.context["stats"]
        self.assertEqual(stats["total"], 2)
        self.assertEqual(dict(stats["breakdown"])["硬件部"], 2)
        self.assertEqual(dict(stats["breakdown"])["软件部"], 0)

    def test_department_is_radio_cards_not_a_dropdown(self):
        """三个选项用卡片：移动端不弹系统选择器，也更适合「选方向」这种决定。"""
        self._login(roles.LEVEL_APPLICANT)
        body = self.client.get(self.url).content.decode()
        self.assertIn('type="radio"', body)
        self.assertIn("rec-choice-item", body)
        self.assertNotIn('<select name="department"', body)
