"""Bounded image decoding shared by member forms, assets and administration."""
import io
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile, UploadedFile
from django.db import models

MAX_UPLOAD_BYTES = 32 * 1024 * 1024
MAX_PIXELS = 64_000_000
MAX_OUTPUT_BYTES = 5 * 1024 * 1024
IMAGE_HELP = '手机原图可直接上传，自动缩放、压缩、摆正并移除EXIF；支持静态JPG、PNG、WebP、BMP、GIF，原图最多32MB / 6400万像素。'
IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp,image/bmp,image/gif'


def encode_variants(upload, maxima=(2048,), preserve_alpha=True):
    if getattr(upload, 'size', 0) > MAX_UPLOAD_BYTES:
        raise ValidationError('原图超过32MB安全上限，请选择较小的原图；已填写的内容不会清空。')
    upload.seek(0)
    raw = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValidationError('原图超过32MB安全上限，请选择较小的原图。')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as probe:
                if probe.format not in {'JPEG', 'PNG', 'WEBP', 'BMP', 'GIF'}:
                    raise ValidationError('暂不支持这种图片格式，请选择JPG、PNG、WebP、BMP或静态GIF。')
                width, height = probe.size
                if width * height > MAX_PIXELS or max(width, height) > 32000:
                    raise ValidationError('原图超过6400万像素或单边32000像素安全上限，请选择较小的原图。')
                if getattr(probe, 'n_frames', 1) != 1:
                    raise ValidationError('这是一张动画，目前只接受静态图片；请选择其中一帧，不会丢弃已填内容。')
                probe.verify()
            with Image.open(io.BytesIO(raw)) as source:
                # JPEG decoder reduction avoids allocating a full phone-sized bitmap.
                # For other codecs, shrink before orientation/conversion copies.
                source.draft('RGB', (max(maxima), max(maxima)))
                source.thumbnail((max(maxima), max(maxima)), Image.Resampling.LANCZOS)
                source = ImageOps.exif_transpose(source)
                alpha = 'A' in source.getbands() or 'transparency' in source.info
                rgba = source.convert('RGBA') if alpha else None
                if alpha and preserve_alpha:
                    source, mode, fmt = rgba, 'RGBA', 'PNG'
                else:
                    clean = Image.new('RGB', source.size, 'white')
                    clean.paste(rgba if alpha else source.convert('RGB'), mask=rgba.getchannel('A') if alpha else None)
                    source, mode, fmt = clean, 'RGB', 'JPEG'
                outputs = []
                for maximum in maxima:
                    resized = source.copy()
                    resized.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
                    while True:
                        # Only decoded pixels survive; no EXIF/profile/comment payload.
                        clean = Image.new(mode, resized.size)
                        clean.paste(resized)
                        buffer = io.BytesIO()
                        clean.save(buffer, fmt, **({'quality': 86, 'optimize': True} if fmt == 'JPEG' else {}))
                        content = buffer.getvalue()
                        if len(content) <= MAX_OUTPUT_BYTES:
                            outputs.append((content, clean.size, fmt))
                            break
                        limit = int(max(resized.size) * .8)
                        if limit < 256:
                            raise ValidationError('图片无法在安全大小内处理，请选择另一张图片。')
                        resized.thumbnail((limit, limit), Image.Resampling.LANCZOS)
                return outputs
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError('图片损坏或无法安全解码，请选择另一张原图；已填内容仍保留。')
    finally:
        upload.seek(0)


def normalize_upload(upload, maximum=2048):
    content, _, fmt = encode_variants(upload, (maximum,))[0]
    name = Path(str(upload.name).replace('\\', '/')).stem[:90] or 'image'
    extension, mime = ('.png', 'image/png') if fmt == 'PNG' else ('.jpg', 'image/jpeg')
    return SimpleUploadedFile(name + extension, content, content_type=mime)


class AutoImageField(forms.FileField):
    widget = forms.ClearableFileInput

    def __init__(self, *args, **kwargs):
        kwargs['help_text'] = (kwargs.get('help_text', '') + ' ' + IMAGE_HELP).strip()
        super().__init__(*args, **kwargs)
        self.widget.attrs['accept'] = IMAGE_ACCEPT

    def to_python(self, data):
        value = super().to_python(data)
        return normalize_upload(value) if isinstance(value, UploadedFile) else value


class AutoImageAdminMixin:
    formfield_overrides = {models.ImageField: {'form_class': AutoImageField}}
