from django import forms
from django.forms import formset_factory
from django.utils import timezone

from news.models import Honor
from projects.models import Project
from .services import validate_people


class PersonForm(forms.Form):
    id = forms.UUIDField(required=False, widget=forms.HiddenInput)
    name = forms.CharField(label='公开署名', max_length=60)
    role = forms.CharField(label='分工 / 获奖身份', max_length=60, required=False)
    cohort = forms.ChoiceField(label='入学届别（可选）', required=False)
    username = forms.CharField(label='已注册用户名（未知留空）', max_length=150, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cohort'].choices = [('', '未知 / 不公开')] + [(str(y), str(y)) for y in range(timezone.localdate().year, 1994, -1)]
        for field in self.fields.values():
            field.widget.attrs['class'] = 'input'


PeopleSet = formset_factory(PersonForm, extra=2, max_num=20, absolute_max=20, validate_max=True, can_delete=True)


def people_set(data, stored):
    if data is not None and 'people-TOTAL_FORMS' in data:
        return PeopleSet(data, prefix='people')
    return PeopleSet(initial=stored or [], prefix='people')


def people_data(formset, stored):
    if not formset.is_bound:
        return validate_people(stored or [])
    return validate_people([{k: str(row.get(k) or '') for k in ('id', 'name', 'role', 'cohort', 'username')}
                            for row in formset.cleaned_data if row and not row.get('DELETE')])


class HonorForm(forms.Form):
    title = forms.CharField(label='奖项全称', max_length=120)
    contest = forms.CharField(label='赛事 / 赛道', max_length=80, required=False)
    year = forms.TypedChoiceField(label='获奖年份', coerce=int)
    level = forms.TypedChoiceField(label='奖项级别', coerce=int, choices=[('', '请选择 / 待核对')] + list(Honor.Level.choices))
    awardee = forms.CharField(label='公开团队署名', max_length=120, help_text='准确填写队伍名或经同意的署名。同一团队同一奖项只录入一次。')
    note = forms.CharField(label='公开说明', max_length=200, required=False, widget=forms.Textarea(attrs={'rows': 3}),
                           help_text='请勿填写手机号、学号或未脱敏证书编号。')
    project = forms.ModelChoiceField(label='关联作品（可选）', queryset=Project.objects.none(), required=False,
                                     help_text='先发布作品，再选它关联奖项；同一作品可以获得多项荣誉。')
    certificate = forms.ModelChoiceField(label='展示证书（可选）', queryset=None, required=False, empty_label='不公开证书')
    upload = forms.FileField(label='上传脱敏证书', required=False, widget=forms.FileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'}),
                             help_text='JPEG / PNG / WebP，5MB / 800 万像素以内。会去除 EXIF，但不会自动遮挡证书内容，请先脱敏。')
    version = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    def __init__(self, draft, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['year'].choices = [('', '请选择获奖年份')] + [(y, str(y)) for y in range(timezone.localdate().year, 1994, -1)]
        self.fields['project'].queryset = Project.public()
        self.fields['certificate'].queryset = draft.images.all()
        for field in self.fields.values():
            field.widget.attrs['class'] = 'input'

    def design(self):
        data = {key: self.cleaned_data[key] for key in ('title', 'contest', 'year', 'level', 'awardee', 'note')}
        data['project'] = self.cleaned_data['project'].pk if self.cleaned_data['project'] else None
        data['certificate'] = str(self.cleaned_data['certificate'].pk) if self.cleaned_data['certificate'] else ''
        return data


class ClaimForm(forms.Form):
    contributor = forms.ModelChoiceField(label='认领已有署名', queryset=None, required=False, empty_label='名单没有我，申请补充')
    public_name = forms.CharField(label='你的公开署名', max_length=60)
    role = forms.CharField(label='你的分工', max_length=60, required=False)
    evidence = forms.CharField(label='核验说明（仅本人和站务可见）', max_length=2000, widget=forms.Textarea(attrs={'rows': 5}),
                               help_text='说明参与时间、分工及可联系的共同参与者。不要填写密码、身份证、学号或手机号码。')
    consent = forms.BooleanField(label='我确认本人参与，且同意经核验后公开这条署名。')

    def __init__(self, item, user, *args, **kwargs):
        from django.db.models import Q
        super().__init__(*args, **kwargs)
        self.fields['contributor'].queryset = item.contributors.filter(active=True, user__isnull=True).filter(Q(invited_user__isnull=True) | Q(invited_user=user))
        self.fields['contributor'].label_from_instance = lambda c: ' · '.join(filter(None, (c.name, c.cohort, c.role)))
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'input'
