from django import forms
from django.core.files.uploadedfile import UploadedFile

from core.models import CarouselImage, MediaSlot, SiteConfig


def _is_new_upload(f) -> bool:
    """这次请求真的带上来了一个新文件吗。

    不要用 `getattr(f, "_committed", True)` 判断：`_committed` 是 `FieldFile`
    的属性，新上传的 `UploadedFile` 根本没有它，于是默认值 True 会让**每一个
    新上传**都被当成「没变」而跳过校验（真实踩过，三条测试同时红）。
    表单里没换文件时 `cleaned_data` 拿到的是 instance 上的 `FieldFile`，
    换了才是 `UploadedFile` —— 直接按类型判断，没有歧义。
    """
    return isinstance(f, UploadedFile)


class SiteConfigForm(forms.ModelForm):
    class Meta:
        model = SiteConfig
        fields = [
            "site_name", "site_name_en", "founding_year",
            "recruit_video_bvid", "recruit_qq_group", "bilibili_mid",
            "featured_video_bvids",
        ]
        widgets = {
            "featured_video_bvids": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{existing} input".strip()


class CarouselImageForm(forms.ModelForm):
    class Meta:
        model = CarouselImage
        fields = ["title", "caption", "image", "sort_order", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name not in ("image", "is_active"):
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{existing} input".strip()


class MediaSlotForm(forms.ModelForm):
    """素材中心的上传/替换表单。

    key 不在表单里：它由 URL/POST 的 action 带过来，并在视图里对着
    core/slots.py 的登记表校验。让站务在表单里手打 key 等于给自己留个
    永远发现不了的错（拼错的槽位只会一直显示占位框）。

    image 对已有记录不是必填：只想改图注或焦点时不该被迫重新上传 ——
    ModelForm 的 FileField 在没有新文件时会沿用 instance 上的旧值。
    """

    # 单个视频文件的硬上限。生产是 2 核 1.6G，视频由 nginx 直出，没有 CDN；
    # 一个几十兆的片子会把带宽吃干。登记表里建议 1.5MB，超过 RECOMMEND 会给
    # 一句提醒但不拦，超过 HARD_LIMIT 直接拒绝。
    VIDEO_HARD_LIMIT = 6 * 1024 * 1024
    VIDEO_RECOMMEND = 1.5 * 1024 * 1024
    VIDEO_EXTENSIONS = {"video_mp4": ".mp4", "video_webm": ".webm"}

    class Meta:
        model = MediaSlot
        fields = ["image", "video_mp4", "video_webm",
                  "alt", "caption", "credit", "focal_x", "focal_y", "is_active"]
        widgets = {
            # 焦点用滑块之外还留了数字框：真正好用的方式是直接点预览图，
            # 由 media_slots.html 里的脚本把点击位置写进这两个框
            "focal_x": forms.NumberInput(attrs={"min": 0, "max": 100, "step": 1}),
            "focal_y": forms.NumberInput(attrs={"min": 0, "max": 100, "step": 1}),
        }

    def __init__(self, *args, **kwargs):
        # 视频槽是图片槽的超集：kind 决定要不要露出那两个视频字段，
        # 以及 image 这一栏叫「图片」还是「封面帧」。
        self.kind = kwargs.pop("kind", "image")
        super().__init__(*args, **kwargs)
        existing_row = bool(self.instance and self.instance.pk)

        if self.kind != "video":
            # 图片槽不该看见视频字段，留着只会让人以为哪里都能传视频
            for name in ("video_mp4", "video_webm"):
                self.fields.pop(name, None)
            self.fields["image"].label = "换一张图（留空保留原图）" if existing_row else "图片"
        else:
            self.fields["image"].label = "封面帧（留空保留原图）" if existing_row else "封面帧"
            self.fields["image"].help_text = (
                "视频加载前显示这一帧，减少动效偏好与省流模式下也只显示它"
            )

        if existing_row:
            self.fields["image"].required = False
        # 一页上有十几份同样的表单，每个字段的说明都重复一遍就成了噪音。
        # 详细说明留在模型的 help_text 里给 Admin 用，这里只留最短的提示。
        self.fields["alt"].help_text = "给读屏软件描述画面内容"
        self.fields["is_active"].help_text = "取消勾选 = 该位置回到占位状态"
        self.fields["focal_x"].help_text = ""
        self.fields["focal_y"].help_text = ""
        for name, field in self.fields.items():
            if name not in ("image", "is_active"):
                existing = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{existing} input".strip()

    @property
    def focal_fields(self):
        """焦点两个字段单独拿出来，模板里并排渲染。

        走通用的 `{% for field in form %}` 循环会让它们各占一行，一张卡片凭空
        高出两行；而它们是一对坐标，本来就该并排。
        """
        return [self["focal_x"], self["focal_y"]]

    @property
    def main_fields(self):
        return [f for f in self if f.name not in ("focal_x", "focal_y")]

    def clean_focal_x(self):
        return self._clean_focal("focal_x")

    def clean_focal_y(self):
        return self._clean_focal("focal_y")

    def _clean_focal(self, name):
        value = self.cleaned_data.get(name)
        if value is None:
            return 50
        if not 0 <= value <= 100:
            raise forms.ValidationError("焦点是百分比，取 0 到 100。")
        return value

    def clean_video_mp4(self):
        return self._clean_video("video_mp4")

    def clean_video_webm(self):
        return self._clean_video("video_webm")

    def _clean_video(self, name):
        """校验扩展名与体积。

        扩展名要卡：这两个字段的值直接进 `<source type="video/mp4">`，传个 .mov
        进去浏览器只会静默不播 —— 又是一个不报错的故障。
        """
        f = self.cleaned_data.get(name)
        if not _is_new_upload(f):
            return f
        want = self.VIDEO_EXTENSIONS[name]
        if not str(f.name).lower().endswith(want):
            raise forms.ValidationError(f"这一栏只接受 {want} 文件，收到的是 {f.name}。")
        if f.size > self.VIDEO_HARD_LIMIT:
            raise forms.ValidationError(
                f"文件 {f.size / 1048576:.1f}MB，超过 "
                f"{self.VIDEO_HARD_LIMIT / 1048576:.0f}MB 上限。"
                "服务器没有 CDN，视频要先压到 720p 无声再传。"
            )
        return f

    def oversized_videos(self) -> list[str]:
        """超出建议体积但没到硬上限的字段，视图拿它提醒站务。"""
        out = []
        for name in self.VIDEO_EXTENSIONS:
            f = getattr(self, "cleaned_data", {}).get(name)
            if _is_new_upload(f) and f.size > self.VIDEO_RECOMMEND:
                out.append(f"{self.fields[name].label}（{f.size / 1048576:.1f}MB）")
        return out
