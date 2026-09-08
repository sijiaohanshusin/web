from urllib.parse import urlsplit

from django import forms

from .models import Project, current_work_year


class WorkForm(forms.Form):
    name = forms.CharField(label="作品名称", max_length=120)
    year = forms.TypedChoiceField(label="作品年份", coerce=int)
    department = forms.ChoiceField(label="方向", choices=Project.Department.choices)
    credit = forms.CharField(label="公开署名与分工", max_length=120, help_text="由你填写，不自动使用档案姓名。共同创作者的署名须征得同意。")
    highlight = forms.CharField(label="一句话亮点", max_length=120, required=False)
    summary = forms.CharField(label="作品介绍", max_length=12000, widget=forms.Textarea(attrs={"rows": 8}), required=False,
                              help_text="可写制作目的、完成情况、技术细节和分工。纯文本段落，不支持 HTML。")
    tags = forms.CharField(label="标签", max_length=120, required=False, help_text="用逗号分隔，例如 STM32, PCB。")
    external_url = forms.URLField(label="公开演示或代码链接", max_length=200, required=False,
                                  help_text="仅 HTTPS，不会自动抓取网页；不要填写私密分享链接。")
    cover = forms.ModelChoiceField(label="封面", queryset=None, required=False, empty_label="暂不使用封面")
    gallery = forms.ModelMultipleChoiceField(label="过程图集", queryset=None, required=False,
                                             widget=forms.CheckboxSelectMultiple, help_text="最多 6 张，按上传顺序展示。")
    upload = forms.FileField(label="上传图片", required=False,
                             widget=forms.FileInput(attrs={"accept": "image/jpeg,image/png,image/webp,image/bmp,image/gif"}),
                             help_text="手机原图自动缩放、压缩与摆正，每次一张，静态图片最多32MB / 6400万像素。上传后存为私有草稿。")
    version = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    def __init__(self, work, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['year'].choices = [(y, str(y)) for y in range(current_work_year(), 1994, -1)]
        self.fields['cover'].queryset = work.images.all()
        self.fields['gallery'].queryset = work.images.all()
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxSelectMultiple, forms.HiddenInput)):
                field.widget.attrs['class'] = 'input'

    def clean_external_url(self):
        value = self.cleaned_data['external_url']
        if value:
            parsed = urlsplit(value)
            if parsed.scheme != 'https' or parsed.username or parsed.password:
                raise forms.ValidationError('请使用不含账号密码的 HTTPS 公开地址。')
        return value

    def clean_gallery(self):
        values = self.cleaned_data['gallery']
        if len(values) > 6:
            raise forms.ValidationError('图集最多选择 6 张图片。')
        return values

    def design(self):
        keys = ('name', 'year', 'department', 'credit', 'highlight', 'summary', 'tags', 'external_url')
        data = {key: self.cleaned_data[key] for key in keys}
        data['cover'] = str(self.cleaned_data['cover'].pk) if self.cleaned_data['cover'] else ''
        data['gallery'] = [str(image.pk) for image in self.cleaned_data['gallery']]
        return data


class WorkRankingForm(forms.Form):
    project = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    importance = forms.IntegerField(label="重要性", min_value=0, max_value=100, widget=forms.NumberInput(attrs={'class': 'input'}))
    is_featured = forms.BooleanField(label="首页精选", required=False)
