"""
AppImage handler: .AppImage packages.
Implements user-mode default installation, FUSE checks, embedded metadata extraction,
and desktop integration according to Section 4-C.
"""

import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.analyzers import (
    check_apparmor_userns_restricted,
    check_elf_arch_compatible,
    check_fuse2_available,
    detect_filesystem_type,
    read_bundled_desktop,
)
from core.desktop_entry import generate_desktop_content
from core.plan import Plan, Step
from core.slug import check_conflicts, derive_slug
from i18n import t


def extract_appimage_metadata(
    appimage_path: Path,
    temp_dir: Path,
) -> Dict[str, Any]:
    """
    Extract embedded metadata (.desktop, .DirIcon, icons) from AppImage.
    """
    metadata: Dict[str, Any] = {
        "name": "",
        "categories": "Utility;",
        "mimetype": "",
        "startup_wm_class": "",
        "icon_file": None,
    }

    try:
        # Run extraction in temp_dir
        for pattern in ["*.desktop", ".DirIcon", "usr/share/icons/*"]:
            subprocess.run(
                [str(appimage_path), "--appimage-extract", pattern],
                cwd=str(temp_dir),
                capture_output=True,
                check=False,
                timeout=10,
            )

        squash_root = temp_dir / "squashfs-root"
        if squash_root.exists():
            # Read .desktop
            desktop_files = list(squash_root.glob("*.desktop"))
            if desktop_files:
                d_info = read_bundled_desktop(desktop_files[0])
                metadata["name"] = d_info.get("name", "")
                metadata["categories"] = d_info.get("categories", "Utility;")
                metadata["mimetype"] = d_info.get("mimetype", "")
                metadata["startup_wm_class"] = d_info.get("startup_wm_class", "")

            # Look for icon
            dir_icon = squash_root / ".DirIcon"
            if dir_icon.exists():
                metadata["icon_file"] = str(dir_icon.resolve())
            else:
                icons = list(squash_root.glob("usr/share/icons/**/*.png")) + list(squash_root.glob("*.png")) + list(squash_root.glob("*.svg"))
                if icons:
                    icons.sort(key=lambda p: p.stat().st_size if p.is_file() else 0, reverse=True)
                    metadata["icon_file"] = str(icons[0].resolve())
    except Exception:
        pass

    return metadata


def build_appimage_plan(file_path: str, options: Optional[Dict[str, Any]] = None) -> Plan:
    """
    Build installation plan for an AppImage.
    Defaults to user mode (~/.local/opt/<slug>/).
    """
    opts = options or {}
    source_p = Path(file_path).resolve()
    filename = source_p.name

    slug = opts.get("slug") or derive_slug(filename)
    if not slug:
        slug = "appimage-app"

    display_name = opts.get("display_name") or slug.replace("-", " ").title()
    mode = opts.get("mode", "user")  # Default to user mode for AppImage!

    warnings: List[str] = []

    # AppImage runtime is an ELF binary, so a wrong-architecture build can be detected up front
    arch_error = check_elf_arch_compatible(source_p)
    if arch_error:
        warnings.append(arch_error)

    # Check filesystem
    fs_type = detect_filesystem_type(str(source_p))
    if fs_type in ("exfat", "vfat", "ntfs", "fuseblk"):
        warnings.append(t("warning_exfat", fs_type=fs_type))

    # Check FUSE
    fuse_ok = check_fuse2_available()
    use_extract_and_run = False
    if not fuse_ok:
        use_extract_and_run = True
        warnings.append(t("warning_fuse2_missing"))

    # Check Ubuntu 24.04 AppArmor userns restriction
    userns_restricted = check_apparmor_userns_restricted()
    allow_no_sandbox = opts.get("allow_no_sandbox", False)
    if userns_restricted:
        warnings.append("نظام أوبونتو 24.04 يقيّد مساحات مستخدم AppArmor غير المميزة. قد تحتاج إضافة --no-sandbox لتطبيقات Electron القديمة.")

    # Paths based on mode
    conflicts = check_conflicts(slug, mode=mode)
    if conflicts["has_conflict"]:
        for msg in conflicts["messages"]:
            warnings.append(msg)

    home = Path.home()
    if mode == "system":
        target_dir = f"/opt/{slug}"
        bin_link = f"/usr/local/bin/{conflicts.get('suggested_bin_name', slug)}"
        desktop_file = f"/usr/share/applications/{conflicts.get('suggested_desktop_filename', f'{slug}.desktop')}"
        icon_dir = f"/usr/share/icons/hicolor/256x256/apps"
        manifest_file = f"/var/lib/smart-installer/{slug}.json"
        needs_root = True
    else:
        target_dir = str(home / ".local/opt" / slug)
        bin_link = str(home / ".local/bin" / conflicts.get("suggested_bin_name", slug))
        desktop_file = str(home / ".local/share/applications" / conflicts.get("suggested_desktop_filename", f"{slug}.desktop"))
        icon_dir = str(home / ".local/share/icons/hicolor/256x256/apps")
        manifest_file = str(home / ".local/share/smart-installer/installs" / f"{slug}.json")
        needs_root = False

    target_appimage_path = os.path.join(target_dir, filename)
    target_icon_path = os.path.join(icon_dir, f"{slug}.png")

    staging_id = f"appimage-{slug}-{uuid.uuid4().hex[:8]}"
    staging_dir = home / ".cache/smart-installer/staging" / staging_id

    # Construct Exec command line
    exec_prefix = "env APPIMAGE_EXTRACT_AND_RUN=1 " if use_extract_and_run else ""
    sandbox_flag = " --no-sandbox" if allow_no_sandbox else ""
    full_exec = f"{exec_prefix}{target_appimage_path}{sandbox_flag}"

    steps: List[Step] = []

    # Step 1: Copy AppImage to target and set chmod +x
    steps.append(
        Step(
            id="copy_appimage",
            title_ar=f"نسخ ملف AppImage إلى {target_dir} وضبط صلاحيات التشغيل (+x)",
            needs_root=needs_root,
            weight=30,
            op="copy_and_chmod",
            args={
                "src": str(source_p),
                "dst_dir": target_dir,
                "dst_file": target_appimage_path,
                "mode": 0o755,
            },
            rollback_op="remove",
            rollback_args={"path": target_dir},
        )
    )

    # Step 2: Extract embedded metadata (desktop & icon)
    steps.append(
        Step(
            id="extract_metadata",
            title_ar="استخراج الأيقونة والمعلومات المدمجة داخل AppImage",
            needs_root=False,
            weight=20,
            op="extract_appimage_metadata",
            args={
                "appimage_path": target_appimage_path,
                "staging_dir": str(staging_dir),
                "target_icon": target_icon_path,
                "slug": slug,
            },
        )
    )

    # Step 3: Symlink in bin
    steps.append(
        Step(
            id="symlink",
            title_ar=f"ربط أمر الطرفية: {bin_link}",
            needs_root=needs_root,
            weight=15,
            op="create_symlink",
            args={"target": target_appimage_path, "link_name": bin_link},
            rollback_op="remove",
            rollback_args={"path": bin_link},
        )
    )

    # Step 4: Create desktop entry
    steps.append(
        Step(
            id="desktop_entry",
            title_ar=f"إنشاء اختصار سطح المكتب: {Path(desktop_file).name}",
            needs_root=needs_root,
            weight=15,
            op="create_desktop_entry",
            args={
                "desktop_file": desktop_file,
                "exec_cmd": full_exec,
                "display_name": display_name,
                "slug": slug,
                "icon": target_icon_path,
            },
            rollback_op="remove",
            rollback_args={"path": desktop_file},
        )
    )

    # Step 5: Update desktop database
    steps.append(
        Step(
            id="update_db",
            title_ar="تحديث قاعدة بيانات التطبيقات",
            needs_root=needs_root,
            weight=10,
            op="update_desktop_database",
            args={"dir": str(Path(desktop_file).parent)},
        )
    )

    # Step 6: Write manifest
    created_paths = [target_dir, bin_link, desktop_file, target_icon_path, manifest_file]
    steps.append(
        Step(
            id="manifest",
            title_ar="تسجيل معلومات التثبيت (Manifest) لدعم إمكانية إلغاء التثبيت",
            needs_root=needs_root,
            weight=10,
            op="write_manifest",
            args={
                "slug": slug,
                "display_name": display_name,
                "mode": mode,
                "format": "appimage",
                "source_file": str(source_p),
                "created_paths": created_paths,
                "manifest_path": manifest_file,
            },
            rollback_op="remove",
            rollback_args={"path": manifest_file},
        )
    )

    return Plan(
        slug=slug,
        display_name=display_name,
        mode=mode,
        format_type="appimage",
        source_file=str(source_p),
        steps=steps,
        staging_dir=str(staging_dir),
        warnings=warnings,
        metadata={
            "target_dir": target_dir,
            "target_appimage_path": target_appimage_path,
            "bin_link": bin_link,
            "desktop_file": desktop_file,
            "manifest_file": manifest_file,
            "target_icon": target_icon_path,
            "fuse_ok": fuse_ok,
            "use_extract_and_run": use_extract_and_run,
        },
    )

