"""
Unit tests for .desktop generation and validation (Section 5.2).
"""

import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.desktop_entry import generate_desktop_content, validate_desktop_file


class TestDesktopEntry(unittest.TestCase):
    """Test desktop entry content generation and FreeDesktop compliance."""

    def test_generate_desktop_content_syntax(self):
        content = generate_desktop_content(
            display_name="Antigravity IDE",
            exec_path="/opt/antigravity/bin/antigravity",
            slug="antigravity",
            icon="/opt/antigravity/icon.png",
            categories="Development;IDE;",
            startup_wm_class="Antigravity",
            name_ar="بيئة التطوير الذكية",
        )

        self.assertIn("[Desktop Entry]", content)
        self.assertIn("Type=Application", content)
        self.assertIn("Version=1.5", content)
        self.assertIn("Name=Antigravity IDE", content)
        self.assertIn("Name[ar]=بيئة التطوير الذكية", content)
        # Exec must be quoted
        self.assertIn('Exec="/opt/antigravity/bin/antigravity" %U', content)
        self.assertIn("TryExec=/opt/antigravity/bin/antigravity", content)
        self.assertIn("Icon=/opt/antigravity/icon.png", content)
        self.assertIn("Categories=Development;IDE;", content)
        self.assertIn("StartupWMClass=Antigravity", content)
        self.assertIn("X-SmartInstaller-Slug=antigravity", content)

    def test_desktop_file_validate_tool(self):
        """Validate generated desktop file using desktop-file-validate."""
        if not shutil.which("desktop-file-validate"):
            self.skipTest("desktop-file-validate not available on host")

        with TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test-app.desktop"
            content = generate_desktop_content(
                display_name="Test App",
                exec_path="/usr/local/bin/test-app",
                slug="test-app",
                categories="Utility;",
            )
            file_path.write_text(content, encoding="utf-8")

            is_valid, msg = validate_desktop_file(str(file_path))
            self.assertTrue(is_valid, f"Validation failed: {msg}")


if __name__ == "__main__":
    unittest.main()

