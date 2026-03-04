#!/usr/bin/env python -O
# -*- coding: utf-8 -*-

import unittest

import mariadb


class TestVersion(unittest.TestCase):
    """Tests for connector version attributes (__version__ and __version_info__)."""

    def _base_version(self) -> str:
        """Return __version__ stripped of PEP 440 local label (+...) and impl suffix (-c)."""
        v = mariadb.__version__
        v = v.split('+')[0]
        if v.endswith('-c'):
            v = v[:-2]
        return v

    def test_version_string_format(self):
        """__version__ must be a non-empty string in X.Y.Z[suffix][+label] format."""
        version = mariadb.__version__
        self.assertIsInstance(version, str)
        self.assertTrue(len(version) > 0)
        base = self._base_version()
        parts = base.split('.')
        self.assertGreaterEqual(len(parts), 3, f"Expected at least 3 dot-separated parts in {base!r}")
        self.assertTrue(parts[0].isdigit(), f"Major version must be numeric, got {parts[0]!r}")
        self.assertTrue(parts[1].isdigit(), f"Minor version must be numeric, got {parts[1]!r}")

    def test_version_info_type(self):
        """__version_info__ must be a tuple of length 3 or 4."""
        version_info = mariadb.__version_info__
        self.assertIsInstance(version_info, tuple)
        self.assertIn(len(version_info), (3, 4))

    def test_version_info_elements(self):
        """First three elements of __version_info__ must be non-negative integers."""
        version_info = mariadb.__version_info__
        for i in range(3):
            self.assertIsInstance(version_info[i], int,
                                  f"version_info[{i}] must be int, got {type(version_info[i])}")
            self.assertGreaterEqual(version_info[i], 0,
                                    f"version_info[{i}] must be >= 0")

    def test_version_info_suffix(self):
        """Optional fourth element of __version_info__ must be a non-empty string."""
        version_info = mariadb.__version_info__
        if len(version_info) == 4:
            self.assertIsInstance(version_info[3], str)
            self.assertTrue(len(version_info[3]) > 0)

    def test_version_info_matches_version_string(self):
        """__version_info__ major/minor/patch must match __version__ numeric segments."""
        version_info = mariadb.__version_info__
        base = self._base_version()
        str_parts = base.split('.')

        self.assertEqual(int(str_parts[0]), version_info[0],
                         f"Major mismatch: {str_parts[0]!r} vs {version_info[0]}")
        self.assertEqual(int(str_parts[1]), version_info[1],
                         f"Minor mismatch: {str_parts[1]!r} vs {version_info[1]}")

        patch_str = str_parts[2]
        # patch_str may be "0" (pure GA) or "0rc1" (pre-release suffix attached).
        # Extract the leading digits and compare against version_info[2] (int),
        # then verify any trailing suffix against version_info[3] (str).
        import re as _re
        patch_match = _re.match(r'^(\d+)([a-zA-Z].*)?$', patch_str)
        self.assertIsNotNone(patch_match, f"Unparseable patch segment: {patch_str!r}")
        patch_num = int(patch_match.group(1))
        patch_suffix = patch_match.group(2) or None
        
        # Handle additional dot-separated components (e.g., "post1" in "2.0.0rc2")
        if len(str_parts) > 3:
            additional_parts = str_parts[3:]
            if patch_suffix:
                patch_suffix = patch_suffix + '.' + '.'.join(additional_parts)
            else:
                patch_suffix = '.'.join(additional_parts)
        
        self.assertEqual(patch_num, version_info[2],
                         f"Patch mismatch: {patch_str!r} vs {version_info[2]}")
        if patch_suffix:
            self.assertGreater(len(version_info), 3,
                               f"version_info has no suffix element for patch suffix {patch_suffix!r}")
            self.assertEqual(patch_suffix, version_info[3],
                             f"Patch suffix mismatch: {patch_suffix!r} vs {version_info[3]!r}")

    def test_version_type(self):
        """__version_type__ must be one of the known implementation identifiers."""
        version_type = mariadb.__version_type__
        self.assertIsInstance(version_type, str)
        self.assertIn(version_type, ('native', 'c', 'binary'))


if __name__ == '__main__':
    unittest.main()
