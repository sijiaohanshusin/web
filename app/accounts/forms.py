import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .choices import COLLEGE_CHOICES, cohort_choices
from .models import ReturningMembershipRequest

User = get_user_model()

_TEXT_INPUT_CLASS = "input"
PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


def _style(fields, skip=()):
    for name, field in fields.items():
        if name in skip:
            continue
        existing = field.widget.attrs.get("class", "")
        field.widget.attrs["class"] = f"{existing} {_TEXT_INPUT_CLASS}".strip()


# ---------------------------------------------------------------- 共用字段工厂
#
# 性别与出生日期出现在**两张表**上：本人的个人资料页（修正入口）和招新报名表
# （首次收集）。写成工厂函数而不是各写一遍 —— 两份定义必然漂移，而这两个字段的
# 麻烦之处恰好都在细节里（空选项的标签、date 输入框的格式），漂了不会报错，
# 只会让其中一页的体验莫名其妙地差一档。
#
# 用函数而不是模块级的字段实例：Django 的表单字段是**有状态的**，同一个实例被
# 两个表单类共用时 widget.attrs 会互相污染（`_style` 就往 attrs 里写 class）。

def GENDER_FIELD():
    """性别。空选项的标签是「不愿透露」而不是 Django 默认的「---------」。

    空串本身就是「不愿透露」，不在 choices 里另设一个枚举值 —— 两种表达同一件
    事，迟早有一处判断只查其中一种。
    """
    return forms.ChoiceField(
        label="性别", required=False,
        choices=[("", "不愿透露"), *User.Gender.choices],
    )


def BIRTHDAY_FIELD():
    """出生日期。

    `format` 和 `input_formats` 都要给：`<input type="date">` 只认 ISO 的
    `YYYY-MM-DD`，而 zh-hans 下 locale 的 `DATE_INPUT_FORMATS[0]` 是 `%Y/%m/%d`
    —— **实测不给 `format` 时渲染出来的是 `value="2005/12/31"`**，浏览器读不懂
    就显示成一个空框。于是用户每次打开资料页保存一次，就顺手把自己的生日清掉了，
    而页面一切正常、没有任何报错。
    钉住它的是 `ProfileApplicantFieldsTests`
    `.test_saved_birthday_is_rendered_back_in_the_format_the_input_expects`
    —— 它断言的是「渲染出来的 value 长什么样」，不是「存进去了没有」。
    """
    return forms.DateField(
        label="出生日期", required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
        help_text="用于生日祝福与分组，不会公开",
    )


class BaseRegisterForm(UserCreationForm):
    username = forms.RegexField(
        label="用户名", regex=r"^[A-Za-z0-9_]{4,20}$", max_length=20,
        error_messages={"invalid": "用户名须为 4-20 位字母、数字或下划线。"},
    )
    real_name = forms.CharField(label="姓名", max_length=30)
    student_id = forms.CharField(label="学号", max_length=20)
    college = forms.ChoiceField(label="学院", choices=[("", "请选择学院"), *COLLEGE_CHOICES])
    grade = forms.ChoiceField(label="届别", choices=[("", "请选择届别"), *cohort_choices()])
    email = forms.EmailField(label="邮箱", help_text="用于接收验证码、找回密码和审核结果")
    phone = forms.CharField(label="手机号", max_length=20)
    qq = forms.CharField(label="QQ 号", max_length=15, required=False)
    code = forms.CharField(label="邮箱验证码", max_length=6, help_text="点击右侧按钮获取")
    specialty = forms.ChoiceField(
        label="擅长方向", choices=[("", "请选择擅长方向"), *User.Specialty.choices],
    )
    specialty_custom = forms.CharField(
        label="自定义方向", max_length=60, required=False,
        help_text="选择“自定义”时必填，例如嵌入式、算法或结构设计",
    )
    privacy_consent = forms.BooleanField(
        label="我已阅读并同意隐私说明",
        help_text="信息仅用于协会身份核验、招新联系和账号安全。",
    )
    website = forms.CharField(required=False, widget=forms.HiddenInput, label="")

    registration_channel = User.RegistrationChannel.NEW

    field_order = [
        "username", "real_name", "student_id", "college", "grade",
        "specialty", "specialty_custom", "email", "code", "phone", "qq",
        "password1", "password2", "privacy_consent", "website",
    ]

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username", "real_name", "student_id", "college", "grade",
            "specialty", "specialty_custom", "email", "phone", "qq",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "登录使用，4-20 位字母、数字或下划线"
        # Django 的 UserCreationForm.__init__ 会给 USERNAME_FIELD 挂 autofocus。
        # 必须摘掉：分步之后 username 在第三段里，而 autofocus 在 HTML 解析时就
        # 生效、比 defer 的 form-enhance.js 早 —— 浏览器把它滚进视口，脚本随后
        # 收起后两段，滚动位置留在原地，结果**页面一进来就停在底部**（标题和
        # 前几个字段都在视口外）。截图才看得出来，控制台一声不响。
        #
        # 也不改成给第一段第一个字段加 autofocus：移动端自动弹键盘会把标题和
        # 进度条全挤出屏幕，而这一页不止表单一样东西。
        self.fields["username"].widget.attrs.pop("autofocus", None)
        _style(self.fields, skip=("privacy_consent", "website"))

    def clean_student_id(self):
        student_id = self.cleaned_data["student_id"].strip()
        if User.objects.filter(student_id=student_id).exists():
            raise forms.ValidationError("该学号已注册，如忘记密码请点击“忘记密码”。")
        return student_id

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("该邮箱已注册，如忘记密码请点击“忘记密码”。")
        return email

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not PHONE_RE.match(phone):
            raise forms.ValidationError("请输入有效的 11 位手机号。")
        if User.objects.filter(phone=phone).exists():
            raise forms.ValidationError("该手机号已注册。")
        return phone

    def clean_qq(self):
        qq = (self.cleaned_data.get("qq") or "").strip()
        if qq and (not qq.isdigit() or not 5 <= len(qq) <= 15):
            raise forms.ValidationError("请输入有效的 QQ 号。")
        return qq

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("website"):
            raise forms.ValidationError("提交未通过安全校验，请刷新后重试。")
        if cleaned.get("specialty") == User.Specialty.CUSTOM:
            custom = (cleaned.get("specialty_custom") or "").strip()
            if not custom:
                self.add_error("specialty_custom", "选择自定义方向时请填写具体方向。")
        else:
            cleaned["specialty_custom"] = ""
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.phone = self.cleaned_data["phone"]
        user.registration_channel = self.registration_channel
        user.specialty = self.cleaned_data["specialty"]
        user.specialty_custom = self.cleaned_data.get("specialty_custom", "")
        if commit:
            user.save()
        return user


class NewMemberRegisterForm(BaseRegisterForm):
    registration_channel = User.RegistrationChannel.NEW


class ReturningMemberRegisterForm(BaseRegisterForm):
    requested_role = forms.ChoiceField(
        label="原协会身份", choices=ReturningMembershipRequest.RequestedRole.choices,
        help_text="请按实际身份申报，管理员会在激活账号前核验。",
    )
    registration_channel = User.RegistrationChannel.RETURNING

    field_order = [
        "username", "real_name", "student_id", "college", "grade", "requested_role",
        "specialty", "specialty_custom", "email", "code", "phone", "qq",
        "password1", "password2", "privacy_consent", "website",
    ]


RegisterForm = NewMemberRegisterForm


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)

    def get_invalid_login_error(self):
        username = self.cleaned_data.get("username")
        if username:
            user = User.objects.filter(username=username).first()
            if user and not user.is_active:
                return forms.ValidationError(
                    "该账号正在等待身份审核，请耐心等待或联系站务管理。", code="inactive"
                )
        return super().get_invalid_login_error()


class CodeLoginForm(forms.Form):
    """验证码登录：邮箱 + 验证码。"""

    email = forms.EmailField(label="邮箱")
    code = forms.CharField(label="验证码", max_length=6)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)


class ForgotPasswordForm(forms.Form):
    """找回密码：邮箱 + 验证码 + 新密码。"""

    email = forms.EmailField(label="邮箱")
    code = forms.CharField(label="验证码", max_length=6)
    new_password1 = forms.CharField(label="新密码", widget=forms.PasswordInput, min_length=8)
    new_password2 = forms.CharField(label="确认新密码", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("new_password1"), cleaned.get("new_password2")
        if p1 and p2 and p1 != p2:
            self.add_error("new_password2", "两次输入的密码不一致。")
        return cleaned


# 个人资料的两组字段。**放模块级**：`class Meta` 的类体看不见外层类的类属性
# （Python 的类作用域不参与嵌套查找），写成 ProfileForm 的属性会直接 NameError。
PROFILE_BASIC_FIELDS = (
    "real_name", "college", "grade", "gender", "birthday",
    "specialty", "specialty_custom", "qq", "phone", "avatar",
)
# Legacy field group stays empty: account edits cannot publish a showcase.
PROFILE_TEAM_FIELDS = ()  # Publication is managed only by the dedicated owner editor.


class ProfileForm(forms.ModelForm):
    college = forms.ChoiceField(label="学院", choices=COLLEGE_CHOICES)
    grade = forms.ChoiceField(label="届别", choices=cohort_choices)
    # 性别与出生日期是招新报名表带进来的两项档案（见 User 上那段注释）。
    # 这里是**本人的修正入口** —— 报名时填错了、或者账号建得比报名表还早的人，
    # 都只能从这一页改。注册表刻意不加这两项：注册链路已经 13 个字段分三段，
    # 而这两项在报名时问一次就够。
    gender = GENDER_FIELD()
    birthday = BIRTHDAY_FIELD()
    specialty = forms.ChoiceField(label="擅长方向", choices=User.Specialty.choices)
    specialty_custom = forms.CharField(label="自定义方向", max_length=60, required=False)

    class Meta:
        model = User
        fields = PROFILE_BASIC_FIELDS + PROFILE_TEAM_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields, skip=("avatar",))

    @property
    def basic_fields(self):
        return [self[name] for name in PROFILE_BASIC_FIELDS if name in self.fields]

    @property
    def team_fields(self):
        return [self[name] for name in PROFILE_TEAM_FIELDS if name in self.fields]

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if phone and not PHONE_RE.match(phone):
            raise forms.ValidationError("请输入有效的 11 位手机号。")
        if phone and User.objects.filter(phone=phone).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("该手机号已被其他账号使用。")
        return phone

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("specialty") == User.Specialty.CUSTOM:
            custom = (cleaned.get("specialty_custom") or "").strip()
            if not custom:
                self.add_error("specialty_custom", "选择自定义方向时请填写具体方向。")
        else:
            cleaned["specialty_custom"] = ""
        return cleaned
