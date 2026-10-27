"""
Unit tests for Plan creation and --dry-run CLI functionality (Section 2.2).
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

from core.plan import build_plan

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MAIN_PY = Path(__file__).parent.parent / "main.py"


class TestPlanGeneration(unittest.TestCase):
    """Test build_plan for various package types."""

    def test_plan_electron_archive(self):
        f = FIXTURES_DIR / "dummy-electron-linux-x64.tar.gz"
        if f.exists():
            plan = build_plan(str(f))
            self.assertEqual(plan.format_type, "archive")
            self.assertEqual(plan.slug, "dummy-electron")
            self.assertEqual(plan.mode, "system")
            self.assertGreater(len(plan.steps), 0)
            self.assertGreater(plan.total_weight, 0)
            # chrome_sandbox step should be present
            step_ids = [s.id for s in plan.steps]
            self.assertIn("chrome_sandbox", step_ids)
            self.assertIn("extract", step_ids)
            self.assertIn("desktop_entry", step_ids)

    def test_plan_deb_package(self):
        f = FIXTURES_DIR / "dummy-tool_1.0.0_all.deb"
        if f.exists():
            plan = build_plan(str(f))
            self.assertEqual(plan.format_type, "deb")
            self.assertEqual(plan.slug, "dummy-tool")
            self.assertEqual(plan.mode, "system")
            step_ids = [s.id for s in plan.steps]
            self.assertIn("prepare_tmp_copy", step_ids)
            self.assertIn("apt_install", step_ids)

    def test_plan_appimage(self):
        f = FIXTURES_DIR / "Obsidian-1.6.7.AppImage"
        if f.exists():
            plan = build_plan(str(f))
            self.assertEqual(plan.format_type, "appimage")
            self.assertEqual(plan.slug, "obsidian")
            # Default for AppImage is user mode!
            self.assertEqual(plan.mode, "user")
            step_ids = [s.id for s in plan.steps]
            self.assertIn("copy_appimage", step_ids)
            self.assertIn("extract_metadata", step_ids)

    def test_plan_script(self):
        f = FIXTURES_DIR / "dummy-installer.sh"
        if f.exists():
            plan = build_plan(str(f))
            self.assertEqual(plan.format_type, "script")
            self.assertEqual(plan.slug, "dummy")
            step_ids = [s.id for s in plan.steps]
            self.assertIn("stage_script", step_ids)
            self.assertIn("run_installer_script", step_ids)


class TestCliDryRun(unittest.TestCase):
    """Test python3 main.py --dry-run CLI execution on all fixtures."""

    def test_dry_run_fixtures(self):
        fixtures = [
            FIXTURES_DIR / "dummy-electron-linux-x64.tar.gz",
            FIXTURES_DIR / "dummy-jetbrains.tar.gz",
            FIXTURES_DIR / "dummy-single-binary.tar.gz",
            FIXTURES_DIR / "dummy-tool_1.0.0_all.deb",
            FIXTURES_DIR / "dummy-installer.sh",
            FIXTURES_DIR / "Obsidian-1.6.7.AppImage",
        ]

        for fix in fixtures:
            if not fix.exists():
                continue
            with self.subTest(fixture=fix.name):
                proc = subprocess.run(
                    [sys.executable, str(MAIN_PY), "--dry-run", str(fix)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(
                    proc.returncode,
                    0,
                    f"--dry-run failed on {fix.name}: {proc.stderr}",
                )
                data = json.loads(proc.stdout)
                self.assertIn("slug", data)
                self.assertIn("display_name", data)
                self.assertIn("steps", data)
                self.assertIsInstance(data["steps"], list)
                self.assertGreater(len(data["steps"]), 0)


if __name__ == "__main__":
    unittest.main()
