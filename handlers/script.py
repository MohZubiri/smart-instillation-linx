"""
Script handler: .sh, .run, .bin.
Implements preview, user approval, terminal execution, and post-install shortcut detection
according to Section 4-D.
"""

import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.analyzers import detect_filesystem_type, preview_script
from core.plan import Plan, Step
from core.slug import derive_slug
from i18n import t


def build_script_plan(file_path: str, options: Optional[Dict[str, Any]] = None) -> Plan:
    """
    Build installation plan for an installer script (.sh, .run, .bin).
    """
    opts = options or {}
    source_p = Path(file_path).resolve()
    filename = source_p.name

    slug = opts.get("slug") or derive_slug(filename)
    if not slug:
        slug = "installer-script"

    display_name = opts.get("display_name") or slug.replace("-", " ").title()
    run_as_root = opts.get("run_as_root", False)
    run_in_terminal = opts.get("run_in_terminal", True)
    extra_args = opts.get("extra_args", [])
    if isinstance(extra_args, str):
        extra_args = extra_args.split()

    warnings: List[str] = []

    # Check filesystem
    fs_type = detect_filesystem_type(str(source_p))
    if fs_type in ("exfat", "vfat", "ntfs", "fuseblk"):
        warnings.append(t("warning_exfat", fs_type=fs_type))

    # Preview script
    preview = preview_script(str(source_p))
    if preview.get("contains_sudo") and not run_as_root:
        warnings.append("يحتوي السكربت على إشارات لأوامر sudo أو مسارات النظام. قد يتطلب تشغيله بصلاحيات الجذر.")

    staging_id = f"script-{slug}-{uuid.uuid4().hex[:8]}"
    staging_dir = Path.home() / ".cache/smart-installer/staging" / staging_id
    staged_script_path = staging_dir / filename

    home = Path.home()
    log_file = str(home / ".local/share/smart-installer/logs" / f"{int(time.time())}-{slug}.log")
    manifest_file = str(
        Path("/var/lib/smart-installer") / f"{slug}.json"
        if run_as_root
        else home / ".local/share/smart-installer/installs" / f"{slug}.json"
    )

    steps: List[Step] = []

    # Step 1: Copy script to staging and set executable (handles exFAT safely)
    steps.append(
        Step(
            id="stage_script",
            title_ar="نسخ سكربت التثبيت وضبط صلاحيات التشغيل (+x)",
            needs_root=False,
            weight=10,
            op="copy_and_chmod",
            args={
                "src": str(source_p),
                "dst_dir": str(staging_dir),
                "dst_file": str(staged_script_path),
                "mode": 0o755,
            },
            rollback_op="rmdir",
            rollback_args={"path": str(staging_dir)},
        )
    )

    # Step 2: Execute script
    steps.append(
        Step(
            id="run_installer_script",
            title_ar=f"تشغيل سكربت التثبيت ({'في الطرفية' if run_in_terminal else 'في السجل الداخلي'})",
            needs_root=run_as_root,
            weight=75,
            op="run_script_step",
            args={
                "script_path": str(staged_script_path),
                "args": extra_args,
                "run_in_terminal": run_in_terminal,
                "run_as_root": run_as_root,
                "cwd": str(source_p.parent),
            },
        )
    )

    # Step 3: Scan for created shortcuts
    steps.append(
        Step(
            id="scan_shortcuts",
            title_ar="البحث عن الاختصارات التي تم إنشاؤها بواسطة السكربت",
            needs_root=False,
            weight=10,
            op="scan_new_desktop_entries",
            args={"start_time": time.time() - 30},
        )
    )

    # Step 4: Write manifest
    steps.append(
        Step(
            id="manifest",
            title_ar="حفظ سجل تشغيل السكربت",
            needs_root=run_as_root,
            weight=5,
            op="write_manifest",
            args={
                "slug": slug,
                "display_name": display_name,
                "mode": "system" if run_as_root else "user",
                "format": "script",
                "source_file": str(source_p),
                "created_paths": [manifest_file],
                "manifest_path": manifest_file,
                "log_path": log_file,
            },
        )
    )

    return Plan(
        slug=slug,
        display_name=display_name,
        mode="system" if run_as_root else "user",
        format_type="script",
        source_file=str(source_p),
        steps=steps,
        staging_dir=str(staging_dir),
        warnings=warnings,
        metadata={
            "run_as_root": run_as_root,
            "run_in_terminal": run_in_terminal,
            "extra_args": extra_args,
            "preview": preview,
            "manifest_file": manifest_file,
        },
    )

