import io
import tempfile

from PIL import Image
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings


def picture(size=(4032, 3024), fmt='JPEG', name='phone.jpg', **kwargs):
    stream = io.BytesIO()
    Image.new('RGB', size, '#377d85').save(stream, fmt, **kwargs)
    return SimpleUploadedFile(name, stream.getvalue(), content_type='application/octet-stream')


class AutomaticImageTests(SimpleTestCase):
    def test_phone_photo_over_eight_megapixels_is_resized(self):
        from showcase.services import encode_image
        for content, size in encode_image(picture()):
            with Image.open(io.BytesIO(content)) as image:
                self.assertEqual(image.size, size)
                self.assertLessEqual(max(size), 1600)
                self.assertFalse(image.getexif())

    def test_large_valid_file_and_wrong_suffix_are_normalized(self):
        from core.image_uploads import normalize_upload
        upload = picture(size=(1600, 1200), fmt='BMP', name='photo.bin')
        self.assertGreater(upload.size, 5 * 1024 * 1024)
        result = normalize_upload(upload)
        self.assertEqual(result.content_type, 'image/jpeg')
        self.assertTrue(result.name.endswith('.jpg'))
        self.assertLess(result.size, 5 * 1024 * 1024)

    def test_orientation_and_transparency_are_preserved_without_metadata(self):
        from core.image_uploads import normalize_upload
        exif = Image.Exif()
        exif[274], exif[270] = 6, 'PRIVATE'
        result = normalize_upload(picture((120, 60), exif=exif))
        with Image.open(result) as image:
            self.assertEqual(image.size, (60, 120))
            self.assertFalse(image.getexif())
        stream = io.BytesIO()
        Image.new('RGBA', (30, 20), (255, 0, 0, 0)).save(stream, 'PNG')
        result = normalize_upload(SimpleUploadedFile('logo.png', stream.getvalue()))
        with Image.open(result) as image:
            self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_unsafe_inputs_have_distinct_errors(self):
        from core.image_uploads import normalize_upload, MAX_UPLOAD_BYTES
        with self.assertRaisesMessage(ValidationError, '32MB'):
            normalize_upload(SimpleUploadedFile('huge.jpg', b'x' * (MAX_UPLOAD_BYTES + 1)))
        with self.assertRaisesMessage(ValidationError, '无法'):
            normalize_upload(SimpleUploadedFile('fake.png', b'<svg onload="bad"/>'))
        stream = io.BytesIO()
        Image.new('RGB', (10, 10)).save(stream, 'WEBP', save_all=True,
            append_images=[Image.new('RGB', (10, 10), 'red')], duration=100)
        with self.assertRaisesMessage(ValidationError, '动画'):
            normalize_upload(SimpleUploadedFile('animation.webp', stream.getvalue()))

    def test_all_main_site_image_forms_use_shared_processor(self):
        from core.image_uploads import AutoImageField
        from accounts.forms import ProfileForm
        from dashboard.forms import CarouselImageForm, MediaSlotForm
        from news.forms import PostForm, HonorForm
        from projects.forms import ProjectForm
        for form, field in ((ProfileForm, 'avatar'), (CarouselImageForm, 'image'),
                            (MediaSlotForm, 'image'), (PostForm, 'cover'),
                            (HonorForm, 'certificate'), (ProjectForm, 'cover')):
            with self.subTest(form=form.__name__):
                self.assertIsInstance(form.base_fields[field], AutoImageField)
                processed = form.base_fields[field].clean(picture())
                with Image.open(processed) as image:
                    self.assertLessEqual(max(image.size), 2048)

    def test_pixel_safety_boundary_is_checked_before_decode(self):
        from unittest.mock import patch, MagicMock
        from core.image_uploads import normalize_upload
        source = MagicMock()
        source.__enter__.return_value = source
        source.format, source.size, source.n_frames = 'PNG', (9000, 9000), 1
        with patch('core.image_uploads.Image.open', return_value=source):
            with self.assertRaisesMessage(ValidationError, '6400'):
                normalize_upload(picture((10, 10)))
        source.load.assert_not_called()


class UploadEndpointTests(TestCase):
    def test_certificate_upload_accepts_phone_photo_without_publishing(self):
        from projects.tests import make_user
        from achievements import honor_services
        from django.urls import reverse
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            owner = make_user('phone-upload')
            draft = honor_services.create(owner)
            self.client.force_login(owner)
            response = self.client.post(reverse('achievements:certificate_upload', args=[draft.pk]),
                                        {'version': draft.version, 'upload': picture()})
            self.assertEqual(response.status_code, 201, response.content)
            draft.refresh_from_db()
            self.assertEqual(draft.draft, {})
            self.assertIsNone(draft.published)
            image = draft.images.get()
            self.assertLessEqual(max(image.width, image.height), 1600)

    def test_inline_images_are_decoded_not_trusted_by_mime(self):
        from projects.tests import make_user
        from django.urls import reverse
        with tempfile.TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            officer = make_user('image-officer', level=4)
            self.client.force_login(officer)
            url = reverse('dashboard:inline_image_upload')
            response = self.client.post(url, {'image': picture()})
            self.assertEqual(response.status_code, 200, response.content)
            response = self.client.post(url, {'image': SimpleUploadedFile('fake.jpg', b'<script>bad</script>', content_type='image/jpeg')})
            self.assertEqual(response.status_code, 400)
