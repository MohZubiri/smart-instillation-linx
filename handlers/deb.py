"""
Deb handler: .deb packages.
Implements package inspection, architecture validation, world-readable staging copy,
and APT installation according to Section 4-B.
"""

import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from core.analyzers import detect_filesystem_type, read_deb_info
from core.plan import Plan, Step
from core.slug import derive_slug
from i18n import t


def get_system_architectures() -> Set[str]:
    """Retrieve primary and foreign system architectures supported by dpkg."""
    archs: Set[str] = {"all"}
    dpkg = shutil.which("dpkg")
    if not dpkg:
        return {"amd64", "all"}

    try:
        p1 = subprocess.run([dpkg, "--print-architecture"], capture_output=True, text=True, check=False)
        if p1.stdout.strip():
            archs.add(p1.stdout.strip())
        p2 = subprocess.run([dpkg, "--print-foreign-architectures"], capture_output=True, text=True, check=False)
        for line in p2.stdout.splitlines():
            if line.strip():
                archs.add(line.strip())
    except Exception:
        archs.add("amd64")

    return archs


def build_deb_plan(file_path: str, options: Optional[Dict[str, Any]] = None) -> Plan:
    """
    Build installation plan for a .deb package.
    """
    opts = options or {}
    source_p = Path(file_path).resolve()
    filename = source_p.name

    # Read deb package metadata
    info = read_deb_info(str(source_p))
    pkg_name = info.get("package") or ""
    pkg_arch = info.get("architecture") or "all"
    pkg_version = info.get("version") or ""
    pkg_desc = info.get("description") or ""

    slug = opts.get("slug") or derive_slug(filename, package_name=pkg_name)
    if not slug:
        slug = pkg_name or "deb-package"

    display_name = opts.get("display_name") or pkg_name or slug.replace("-", " ").title()

    warnings: List[str] = []

    # Validate architecture
    sys_archs = get_system_architectures()
    if pkg_arch != "all" and pkg_arch not in sys_archs:
        primary_arch = next((a for a in sys_archs if a != "all"), "amd64")
        raise ValueError(
            t("warning_arch_mismatch", pkg_arch=pkg_arch, sys_arch=primary_arch)
        )

    # Check filesystem
    fs_type = detect_filesystem_type(str(source_p))
    if fs_type in ("exfat", "vfat", "ntfs", "fuseblk"):
        warnings.append(t("warning_exfat", fs_type=fs_type))

    # Stage directory in world-readable /tmp (0755 folder, 0644 file) so _apt user can read it
    temp_id = f"smart-installer-{uuid.uuid4().hex[:8]}"
    temp_dir = Path("/tmp") / temp_id
    temp_deb_path = temp_dir / filename
    manifest_file = f"/var/lib/smart-installer/{slug}.json"

    steps: List[Step] = []

    # Step 1: Copy to world-readable /tmp directory
    steps.append(
        Step(
            id="prepare_tmp_copy",
            title_ar="نسخ الحزمة إلى مجلد مؤقت قابل للقراءة من مستخدم النظام (_apt)",
            needs_root=False,
            weight=15,
            op="copy_deb_to_tmp",
            args={
                "src": str(source_p),
                "dst_dir": str(temp_dir),
                "dst_file": str(temp_deb_path),
            },
            rollback_op="rmdir",
            rollback_args={"path": str(temp_dir)},
        )
    )

    # Step 2: Install via APT with Status-Fd
    steps.append(
        Step(
            id="apt_install",
            title_ar=f"تثبيت الحزمة {pkg_name} عبر APT مع حل الاعتماديات تلقائياً",
            needs_root=True,
            weight=70,
            op="apt_install_deb",
            args={"deb_path": str(temp_deb_path)},
        )
    )

    # Step 3: Register manifest
    steps.append(
        Step(
            id="manifest",
            title_ar="تسجيل معلومات التثبيت (Manifest) في سجل النظام",
            needs_root=True,
            weight=10,
            op="write_manifest",
            args={
                "slug": slug,
                "display_name": display_name,
                "mode": "system",
                "format": "deb",
                "source_file": str(source_p),
                "deb_package": pkg_name,
                "created_paths": [manifest_file],
                "manifest_path": manifest_file,
            },
            rollback_op="remove",
            rollback_args={"path": manifest_file},
        )
    )

    # Step 4: Cleanup temp directory
    steps.append(
        Step(
            id="cleanup_tmp",
            title_ar="حذف المجلد المؤقت بعد اكتمال التثبيت",
            needs_root=False,
            weight=5,
            op="cleanup_tmp",
            args={"path": str(temp_dir)},
        )
    )

    return Plan(
        slug=slug,
        display_name=display_name,
        mode="system",
        format_type="deb",
        source_file=str(source_p),
        steps=steps,
        staging_dir=str(temp_dir),
        warnings=warnings,
        metadata={
            "package_name": pkg_name,
            "version": pkg_version,
            "architecture": pkg_arch,
            "description": pkg_desc,
            "temp_deb_path": str(temp_deb_path),
            "manifest_file": manifest_file,
            "desktop_file": info.get("desktop_file"),
        },
    )

