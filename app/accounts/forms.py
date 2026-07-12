from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

User = get_user_model()

_TEXT_INPUT_CLASS = "input"


class RegisterForm(UserCreationForm):
    real_name = forms.CharField(label="姓名", max_length=30)
    student_id = forms.CharField(label="学号", max_length=20)
    college = forms.CharField(label="学院", max_length=50)
    grade = forms.CharField(label="年级", max_length=10, help_text="入学年份，如 2025")
    qq = forms.CharField(label="QQ 号", max_length=15, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "real_name", "student_id", "college", "grade", "qq")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "登录用，4-20 位字母、数字或下划线"
        for field in self.fields.values():
            css = _TEXT_INPUT_CLASS
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {css}".strip()

    def clean_student_id(self):
        student_id = self.cleaned_data["student_id"].strip()
        if User.objects.filter(student_id=student_id).exists():
            raise forms.ValidationError("该学号已注册，如忘记密码请联系管理员。")
        return student_id

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_active = False  # 注册后待管理员审核
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} {_TEXT_INPUT_CLASS}".strip()

    def get_invalid_login_error(self):
        # 账号存在但未激活时，给出“待审核”提示而不是“密码错误”
        username = self.cleaned_data.get("username")
        if username:
            user = User.objects.filter(username=username).first()
            if user and not user.is_active:
                return forms.ValidationError(
                    "该账号正在等待管理员审核，请耐心等待或联系干事。", code="inactive"
                )
        return super().get_invalid_login_error()


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("real_name", "college", "grade", "qq", "avatar")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != "avatar":
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{existing} {_TEXT_INPUT_CLASS}".strip()
