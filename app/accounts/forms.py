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


class ProfileForm(forms.ModelForm):
    college = forms.ChoiceField(label="学院", choices=COLLEGE_CHOICES)
    grade = forms.ChoiceField(label="届别", choices=cohort_choices)
    specialty = forms.ChoiceField(label="擅长方向", choices=User.Specialty.choices)
    specialty_custom = forms.CharField(label="自定义方向", max_length=60, required=False)

    class Meta:
        model = User
        fields = (
            "real_name", "college", "grade", "specialty", "specialty_custom",
            "qq", "phone", "avatar",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields, skip=("avatar",))

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
