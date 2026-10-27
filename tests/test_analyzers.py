"""
Unit tests for analyzers: format detection, executable discovery, icon discovery,
electron WMClass, and script preview.
"""

import os
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.analyzers import (
    check_elf_arch_compatible,
    get_elf_machine,
    detect_electron_wmclass,
    detect_format,
    find_executable,
    find_icon,
    inspect_archive,
    is_excluded_executable,
    is_gui_executable,
    preview_script,
    read_deb_info,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestAnalyzers(unittest.TestCase):
    """Test package analysis functions."""

    def test_detect_format(self):
        self.assertEqual(detect_format("test.deb"), "deb")
        self.assertEqual(detect_format("test.tar.gz"), "archive")
        self.assertEqual(detect_format("test.tgz"), "archive")
        self.assertEqual(detect_format("test.tar.xz"), "archive")
        self.assertEqual(detect_format("test.tar.bz2"), "archive")
        self.assertEqual(detect_format("test.zip"), "archive")
        self.assertEqual(detect_format("test.AppImage"), "appimage")
        self.assertEqual(detect_format("test.sh"), "script")
        self.assertEqual(detect_format("test.run"), "script")
        self.assertEqual(detect_format("test.bin"), "script")

    def test_inspect_archive_safe(self):
        arch = FIXTURES_DIR / "dummy-jetbrains.tar.gz"
        if arch.exists():
            res = inspect_archive(str(arch))
            self.assertTrue(res["valid"])
            self.assertGreater(res["member_count"], 0)
            self.assertGreater(res["uncompressed_size"], 0)

    def test_inspect_archive_rejects_traversal(self):
        with TemporaryDirectory() as temp_dir:
            bad_tar = Path(temp_dir) / "bad.tar.gz"
            with tarfile.open(bad_tar, "w:gz") as tf:
                # Add entry with .. traversal
                ti = tarfile.TarInfo(name="../escape.txt")
                ti.size = 0
                tf.addfile(ti)

            res = inspect_archive(str(bad_tar))
            self.assertFalse(res["valid"])
            self.assertIn("..", res["error"])

    def test_find_executable_jetbrains(self):
        """JetBrains archive: bin/idea.sh should be discovered."""
        arch = FIXTURES_DIR / "dummy-jetbrains.tar.gz"
        if arch.exists():
            with TemporaryDirectory() as temp_dir:
                with tarfile.open(arch, "r:gz") as tf:
                    if hasattr(tarfile, "data_filter"):
                        tf.extractall(temp_dir, filter="data")
                    else:
                        tf.extractall(temp_dir)
                root = Path(temp_dir) / "dummy-jetbrains"
                exe, candidates = find_executable(root, "jetbrains")
                self.assertIsNotNone(exe)
                self.assertEqual(exe.name, "idea.sh")

    def test_find_icon_jetbrains(self):
        """JetBrains archive: bin/idea.svg should be discovered."""
        arch = FIXTURES_DIR / "dummy-jetbrains.tar.gz"
        if arch.exists():
            with TemporaryDirectory() as temp_dir:
                with tarfile.open(arch, "r:gz") as tf:
                    if hasattr(tarfile, "data_filter"):
                        tf.extractall(temp_dir, filter="data")
                    else:
                        tf.extractall(temp_dir)
                root = Path(temp_dir) / "dummy-jetbrains"
                icon = find_icon(root, "jetbrains")
                self.assertIsNotNone(icon)
                self.assertEqual(icon.name, "idea.svg")

    def test_find_executable_electron(self):
        """Electron archive: dummy-electron should be discovered and chrome-sandbox excluded."""
        arch = FIXTURES_DIR / "dummy-electron-linux-x64.tar.gz"
        if arch.exists():
            with TemporaryDirectory() as temp_dir:
                with tarfile.open(arch, "r:gz") as tf:
                    if hasattr(tarfile, "data_filter"):
                        tf.extractall(temp_dir, filter="data")
                    else:
                        tf.extractall(temp_dir)
                root = Path(temp_dir) / "dummy-electron"
                exe, candidates = find_executable(root, "dummy-electron")
                self.assertIsNotNone(exe)
                self.assertEqual(exe.name, "dummy-electron")

    def test_detect_electron_wmclass(self):
        """Should read productName 'Dummy Electron' from package.json."""
        arch = FIXTURES_DIR / "dummy-electron-linux-x64.tar.gz"
        if arch.exists():
            with TemporaryDirectory() as temp_dir:
                with tarfile.open(arch, "r:gz") as tf:
                    if hasattr(tarfile, "data_filter"):
                        tf.extractall(temp_dir, filter="data")
                    else:
                        tf.extractall(temp_dir)
                root = Path(temp_dir) / "dummy-electron"
                wm_class = detect_electron_wmclass(root)
                self.assertEqual(wm_class, "Dummy Electron")

    def test_elf_arch_check(self):
        with TemporaryDirectory() as tmp:
            def make_elf(name: str, machine: int) -> Path:
                p = Path(tmp) / name
                p.write_bytes(b"\x7fELF\x02\x01\x01" + b"\x00" * 9 + b"\x03\x00" + machine.to_bytes(2, "little") + b"\x00" * 44)
                return p

            arm = make_elf("arm-app", 0xB7)
            x64 = make_elf("x64-app", 0x3E)
            self.assertEqual(get_elf_machine(arm), "aarch64")
            self.assertEqual(get_elf_machine(x64), "x86_64")
            host = os.uname().machine
            native = x64 if host == "x86_64" else arm
            foreign = arm if host == "x86_64" else x64
            self.assertIsNone(check_elf_arch_compatible(native))
            self.assertIsNotNone(check_elf_arch_compatible(foreign))

    def test_preview_script(self):
        sh_file = FIXTURES_DIR / "dummy-installer.sh"
        if sh_file.exists():
            res = preview_script(str(sh_file))
            self.assertGreater(res["size"], 0)
            self.assertTrue(len(res["sha256"]) == 64)
            self.assertIn("#!/bin/bash", res["first_lines"][0])

    def test_read_deb_info(self):
        deb_file = FIXTURES_DIR / "dummy-tool_1.0.0_all.deb"
        if deb_file.exists():
            info = read_deb_info(str(deb_file))
            self.assertEqual(info["package"], "dummy-tool")
            self.assertEqual(info["version"], "1.0.0")
            self.assertEqual(info["architecture"], "all")
            self.assertEqual(info["desktop_file"], "/usr/share/applications/dummy-tool.desktop")


    def test_is_excluded_executable(self):
        self.assertTrue(is_excluded_executable("default.sfx"))
        self.assertTrue(is_excluded_executable("module.sfx"))
        self.assertTrue(is_excluded_executable("chrome-sandbox"))
        self.assertTrue(is_excluded_executable("makefile"))
        self.assertFalse(is_excluded_executable("rar"))
        self.assertFalse(is_excluded_executable("antigravity"))

    def test_find_executable_ranking(self):
        with TemporaryDirectory() as temp_dir:
            p = Path(temp_dir)
            elf_fixture = FIXTURES_DIR / "dummy-single-binary.tar.gz"
            # Read minimal ELF bytes from fixture
            import tarfile
            with tarfile.open(elf_fixture, "r:gz") as tf:
                elf_bytes = tf.extractfile("mycli").read()

            # Create mock binaries
            (p / "default.sfx").write_bytes(elf_bytes)
            (p / "unrar").write_bytes(elf_bytes)
            (p / "rar").write_bytes(elf_bytes)

            exe, candidates = find_executable(p, "rarlinux-723")
            self.assertIsNotNone(exe)
            self.assertEqual(exe.name, "rar")


if __name__ == "__main__":
    unittest.main()
