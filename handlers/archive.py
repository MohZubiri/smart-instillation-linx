"""
Archive handler: .tar.gz, .tar.xz, .tar.bz2, .tgz, .zip.
Implements complete archive installation logic according to Section 4-A.
"""

import os
import shutil
import tarfile
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.analyzers import (
    detect_electron_wmclass,
    detect_filesystem_type,
    find_executable,
    find_icon,
    inspect_archive,
    read_bundled_desktop,
)
from core.desktop_entry import generate_desktop_content
from core.plan import Plan, Step
from core.slug import check_conflicts, derive_slug
from i18n import t


def extract_archive_safely(
    archive_path: str,
    target_dir: str,
    progress_cb: Optional[Any] = None,
) -> None:
    """
    Extract archive into staging directory without root permissions.
    Uses filter='data' in Python 3.12+ for tarfile.
    """
    p = Path(archive_path)
    lower = p.name.lower()
    os.makedirs(target_dir, exist_ok=True)

    if lower.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            members = zf.infolist()
            total = len(members)
            for i, member in enumerate(members):
                # Safe extract
                zf.extract(member, target_dir)
                if progress_cb and total > 0 and (i % 25 == 0 or i == total - 1):
                    progress_cb(int((i + 1) / total * 100), f"فك الضغط: {member.filename}")
    else:
        with tarfile.open(archive_path, "r:*") as tf:
            # Check if filter='data' supported (Python 3.12+)
            if hasattr(tarfile, "data_filter"):
                tf.extractall(target_dir, filter="data")
            else:
                # Python 3.10 / 3.11 safe extraction
                for m in tf.getmembers():
                    if m.name.startswith("/") or ".." in Path(m.name).parts:
                        continue
                    tf.extract(m, target_dir)


def flatten_extracted_tree(staging_root: Path) -> None:
    """
    Flatten staging directory if it contains only a single root folder.
    """
    items = [x for x in staging_root.iterdir() if x.name != "__MACOSX"]
    if len(items) == 1 and items[0].is_dir():
        single_dir = items[0]
        # Move all contents of single_dir to staging_root
        temp_dir = staging_root.parent / f"{staging_root.name}_temp"
        shutil.move(str(single_dir), str(temp_dir))
        for sub in temp_dir.iterdir():
            shutil.move(str(sub), str(staging_root / sub.name))
        shutil.rmtree(str(temp_dir), ignore_errors=True)


def build_archive_plan(file_path: str, options: Optional[Dict[str, Any]] = None) -> Plan:
    """
    Build installation plan for an archive (.tar.*, .zip).
    """
    opts = options or {}
    source_p = Path(file_path).resolve()
    filename = source_p.name

    slug = opts.get("slug") or derive_slug(filename)
    if not slug:
        slug = "app"

    display_name = opts.get("display_name") or slug.replace("-", " ").title()
    mode = opts.get("mode", "system")  # "system" or "user"

    staging_id = f"{slug}-{uuid.uuid4().hex[:8]}"
    staging_dir = Path.home() / ".cache/smart-installer/staging" / staging_id

    warnings: List[str] = []

    # Check filesystem of source
    fs_type = detect_filesystem_type(str(source_p))
    if fs_type in ("exfat", "vfat", "ntfs", "fuseblk"):
        warnings.append(t("warning_exfat", fs_type=fs_type))

    # Inspect archive for member count and size
    inspection = inspect_archive(str(source_p))
    if not inspection["valid"]:
        raise ValueError(inspection["error"] or "الأرشيف غير صالح أو به ملفات مشبوهة")

    uncompressed_mb = inspection["uncompressed_size"] // (1024 * 1024)

    # Check destination paths and conflicts
    conflicts = check_conflicts(slug, mode=mode)
    if conflicts["has_conflict"]:
        for msg in conflicts["messages"]:
            warnings.append(msg)

    if mode == "system":
        target_dir = f"/opt/{slug}"
        bin_link = f"/usr/local/bin/{conflicts.get('suggested_bin_name', slug)}"
        desktop_file = f"/usr/share/applications/{conflicts.get('suggested_desktop_filename', f'{slug}.desktop')}"
        manifest_file = f"/var/lib/smart-installer/{slug}.json"
        needs_root_for_install = True
    else:
        home = Path.home()
        target_dir = str(home / ".local/opt" / slug)
        bin_link = str(home / ".local/bin" / conflicts.get("suggested_bin_name", slug))
        desktop_file = str(home / ".local/share/applications" / conflicts.get("suggested_desktop_filename", f"{slug}.desktop"))
        manifest_file = str(home / ".local/share/smart-installer/installs" / f"{slug}.json")
        needs_root_for_install = False

    # Check available disk space
    try:
        check_path = "/opt" if mode == "system" else str(Path.home())
        free_mb = shutil.disk_usage(check_path).free // (1024 * 1024)
        if free_mb < uncompressed_mb * 2:
            warnings.append(t("warning_space", avail=free_mb, needed=uncompressed_mb * 2))
    except Exception:
        pass

    # Build sequence of Steps
    steps: List[Step] = []

    # Step 1: Extract in staging (user space)
    steps.append(
        Step(
            id="extract",
            title_ar="فك ضغط الأرشيف في مجلد التحضير",
            needs_root=False,
            weight=30,
            op="extract_archive",
            args={"source": str(source_p), "target": str(staging_dir)},
            rollback_op="rmdir",
            rollback_args={"path": str(staging_dir)},
        )
    )

    # Step 2: Inspect staging, detect executable, icon, and chrome-sandbox
    steps.append(
        Step(
            id="inspect",
            title_ar="فحص محتويات الحزمة واكتشاف الملف التنفيذي والأيقونة",
            needs_root=False,
            weight=10,
            op="inspect_staging",
            args={"staging_dir": str(staging_dir), "slug": slug},
        )
    )

    # Step 3: Move tree to target directory
    steps.append(
        Step(
            id="move_tree",
            title_ar=f"نقل ملفات البرنامج إلى {target_dir}",
            needs_root=needs_root_for_install,
            weight=20,
            op="move_tree",
            args={"src": str(staging_dir), "dst": target_dir},
            rollback_op="remove",
            rollback_args={"path": target_dir},
        )
    )

    # Step 4: Fix chrome-sandbox permissions if present (always requires root)
    steps.append(
        Step(
            id="chrome_sandbox",
            title_ar="فحص وإصلاح صلاحيات chrome-sandbox (إن وُجد)",
            needs_root=True,
            weight=5,
            op="fix_chrome_sandbox",
            args={"target_dir": target_dir},
        )
    )

    # Step 5: Create terminal symlink
    steps.append(
        Step(
            id="symlink",
            title_ar=f"ربط أمر الطرفية: {bin_link}",
            needs_root=needs_root_for_install,
            weight=10,
            op="create_symlink",
            args={"link_name": bin_link, "target_dir": target_dir, "slug": slug},
            rollback_op="remove",
            rollback_args={"path": bin_link},
        )
    )

    # Step 6: Create .desktop shortcut
    steps.append(
        Step(
            id="desktop_entry",
            title_ar=f"إنشاء اختصار في قائمة التطبيقات: {Path(desktop_file).name}",
            needs_root=needs_root_for_install,
            weight=10,
            op="create_desktop_entry",
            args={
                "desktop_file": desktop_file,
                "target_dir": target_dir,
                "display_name": display_name,
                "slug": slug,
            },
            rollback_op="remove",
            rollback_args={"path": desktop_file},
        )
    )

    # Step 7: Update desktop database
    steps.append(
        Step(
            id="update_db",
            title_ar="تحديث قاعدة بيانات اختصارات سطح المكتب",
            needs_root=needs_root_for_install,
            weight=5,
            op="update_desktop_database",
            args={"dir": str(Path(desktop_file).parent)},
        )
    )

    # Step 8: Write manifest
    steps.append(
        Step(
            id="manifest",
            title_ar="تسجيل معلومات التثبيت (Manifest) لدعم إمكانية إلغاء التثبيت",
            needs_root=needs_root_for_install,
            weight=10,
            op="write_manifest",
            args={
                "slug": slug,
                "display_name": display_name,
                "mode": mode,
                "format": "archive",
                "source_file": str(source_p),
                "created_paths": [target_dir, bin_link, desktop_file, manifest_file],
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
        format_type="archive",
        source_file=str(source_p),
        steps=steps,
        staging_dir=str(staging_dir),
        warnings=warnings,
        metadata={
            "target_dir": target_dir,
            "bin_link": bin_link,
            "desktop_file": desktop_file,
            "manifest_file": manifest_file,
            "uncompressed_mb": uncompressed_mb,
        },
    )

