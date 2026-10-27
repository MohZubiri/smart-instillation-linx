"""
Unit tests for privileged helper security: path verification and operation whitelisting
(Section 2.1).
"""

import unittest
from privileged_helper import is_path_allowed, validate_batch


class TestHelperSecurity(unittest.TestCase):
    """Test privileged helper security checks and path containment."""

    def test_allowed_paths(self):
        staging = "/home/user/.cache/smart-installer/staging/test-uuid"

        # Allowed system roots
        self.assertTrue(is_path_allowed("/opt/my-app"))
        self.assertTrue(is_path_allowed("/opt/my-app/bin/start"))
        self.assertTrue(is_path_allowed("/usr/local/bin/my-app"))
        self.assertTrue(is_path_allowed("/usr/share/applications/my-app.desktop"))
        self.assertTrue(is_path_allowed("/usr/share/icons/hicolor/256x256/apps/my-app.png"))
        self.assertTrue(is_path_allowed("/var/lib/smart-installer/my-app.json"))
        self.assertTrue(is_path_allowed("/tmp/smart-installer-123/pkg.deb"))

        # Allowed staging path
        self.assertTrue(is_path_allowed(staging + "/extracted/bin", staging_dir=staging))

    def test_rejected_unauthorized_paths(self):
        staging = "/home/user/.cache/smart-installer/staging/test-uuid"

        self.assertFalse(is_path_allowed("/etc/passwd"))
        self.assertFalse(is_path_allowed("/etc/shadow"))
        self.assertFalse(is_path_allowed("/root/.bashrc"))
        self.assertFalse(is_path_allowed("/var/www/html"))
        self.assertFalse(is_path_allowed("/usr/bin/python3"))
        self.assertFalse(is_path_allowed("/home/otheruser/.ssh/id_rsa", staging_dir=staging))
        self.assertFalse(is_path_allowed("/opt/../etc/passwd"))

    def test_validate_batch_operations(self):
        # Valid batch
        valid_ops = [
            {"op": "mkdir", "args": {"path": "/opt/test-app"}},
            {"op": "symlink", "args": {"target": "/opt/test-app/bin", "link_name": "/usr/local/bin/test-app"}},
            {"op": "update_desktop_database", "args": {"dir": "/usr/share/applications"}},
        ]
        err = validate_batch(valid_ops)
        self.assertIsNone(err)

        # Disallowed operation
        bad_op = [
            {"op": "unauthorized_exec", "args": {"path": "/opt/test-app"}}
        ]
        err = validate_batch(bad_op)
        self.assertIsNotNone(err)
        self.assertIn("عملية غير مسموحة", err)

        # Disallowed path inside valid operation
        bad_path = [
            {"op": "mkdir", "args": {"path": "/etc/malicious_dir"}}
        ]
        err = validate_batch(bad_path)
        self.assertIsNotNone(err)
        self.assertIn("مسار غير مصرح به", err)


if __name__ == "__main__":
    unittest.main()

