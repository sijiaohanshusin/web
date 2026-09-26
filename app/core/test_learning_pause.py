from django.test import TestCase


class LearningPauseTests(TestCase):
    def test_saved_chapter_and_asset_urls_do_not_expose_unreviewed_material(self):
        for path in ("/learn", "/learn/", "/learn/electronics/",
                     "/learn/electronics/pages/chapter01.html",
                     "/learn/electronics/assets/course.pdf"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertContains(response, "学习资料整理中")
                self.assertContains(response, 'href="/recruit/"')
                self.assertIn("no-store", response["Cache-Control"])
                self.assertIn("noindex", response["X-Robots-Tag"])

    def test_public_entry_points_no_longer_advertise_the_material(self):
        for path in ("/", "/recruit/", "/resources/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, 'href="/learn/')
                self.assertNotContains(response, "27 章自编教材")
