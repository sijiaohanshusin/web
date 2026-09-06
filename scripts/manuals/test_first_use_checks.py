"""Regression cases for release labels versus a member's draft state."""
import unittest

from check_first_use import release_boundary_errors


class ReleaseBoundaryTests(unittest.TestCase):
    def test_unpublished_member_drafts_are_valid_in_a_released_manual(self):
        self.assertEqual(release_boundary_errors(
            'published', '适用正式站 ede30a6', '不是随后修改但尚未发布的草稿。'), [])

    def test_unreleased_feature_label_is_rejected_on_the_cover(self):
        for label in ('功能尚未上线', '本功能尚未发布', '网站候选版本', '本次待上线功能'):
            with self.subTest(label=label):
                self.assertTrue(release_boundary_errors('published', label, label))

    def test_candidate_cover_must_state_release_boundary(self):
        self.assertTrue(release_boundary_errors('candidate', '隔离环境验证', ''))
        self.assertEqual(release_boundary_errors('candidate', '本次待上线功能', ''), [])

    def test_unreleased_feature_label_in_body_is_not_ignored(self):
        self.assertTrue(release_boundary_errors('published', '正式版本', '本功能尚未上线'))


if __name__ == '__main__':
    unittest.main()
