"""
Unit tests for slug derivation and conflict detection (Section 5.1 and 5.4).
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.slug import check_conflicts, derive_slug, strip_extension


class TestSlugDerivation(unittest.TestCase):
    """Test derive_slug against Section 5.1 specifications and examples."""

    def test_strip_compound_extensions(self):
        self.assertEqual(strip_extension("app.tar.gz"), "app")
        self.assertEqual(strip_extension("app.tar.xz"), "app")
        self.assertEqual(strip_extension("app.tar.bz2"), "app")
        self.assertEqual(strip_extension("app.tgz"), "app")
        self.assertEqual(strip_extension("app.zip"), "app")
        self.assertEqual(strip_extension("app.AppImage"), "app")
        self.assertEqual(strip_extension("app.deb"), "app")
        self.assertEqual(strip_extension("app.sh"), "app")
        self.assertEqual(strip_extension("app.run"), "app")

    def test_spec_table_examples(self):
        # 1. Antigravity-IDE_1.2.3-linux-x64.tar.gz -> antigravity-ide
        self.assertEqual(
            derive_slug("Antigravity-IDE_1.2.3-linux-x64.tar.gz"),
            "antigravity-ide",
        )

        # 2. Postman-linux-x64-11.0.5.tar.gz -> postman
        self.assertEqual(
            derive_slug("Postman-linux-x64-11.0.5.tar.gz"),
            "postman",
        )

        # 3. Obsidian-1.6.7.AppImage -> obsidian
        self.assertEqual(
            derive_slug("Obsidian-1.6.7.AppImage"),
            "obsidian",
        )

        # 4. code_1.93.1-1726079302_amd64.deb with package field 'code' -> code
        self.assertEqual(
            derive_slug("code_1.93.1-1726079302_amd64.deb", package_name="code"),
            "code",
        )

        # 5. Miniconda3-latest-Linux-x86_64.sh -> miniconda3
        self.assertEqual(
            derive_slug("Miniconda3-latest-Linux-x86_64.sh"),
            "miniconda3",
        )

    def test_edge_cases(self):
        # Consecutive hyphens
        self.assertEqual(derive_slug("My---App___Name--v1.0.tar.gz"), "my-app-name")
        # Empty when non-ascii only
        self.assertEqual(derive_slug("برنامج-تجريبي.tar.gz"), "")


class TestSlugConflicts(unittest.TestCase):
    """Test conflict detection rules (Section 5.4)."""

    def test_no_conflict_clean_env(self):
        with TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            conflicts = check_conflicts("unique-test-app-xyz", mode="user", user_home=home)
            self.assertFalse(conflicts["has_conflict"])
            self.assertEqual(conflicts["suggested_bin_name"], "unique-test-app-xyz")

    def test_target_dir_with_manifest_upgrade(self):
        with TemporaryDirectory() as temp_dir:
            home = Path(temp_dir)
            slug = "my-test-app"
            target = home / ".local/opt" / slug
            target.mkdir(parents=True)
            manifest = home / ".local/share/smart-installer/installs" / f"{slug}.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text("{}", encoding="utf-8")

            conflicts = check_conflicts(slug, mode="user", user_home=home)
            self.assertTrue(conflicts["has_conflict"])
            self.assertTrue(conflicts["target_exists"])
            self.assertTrue(conflicts["has_manifest"])
            self.assertEqual(conflicts["action_required"], "upgrade")


if __name__ == "__main__":
    unittest.main()

