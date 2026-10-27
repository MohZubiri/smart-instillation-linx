"""
Slug derivation and conflict detection module.
Follows rules defined in Section 5.1 and 5.4.
"""

import os
import re
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

COMPOUND_EXTENSIONS = [
    ".tar.gz",
    ".tar.xz",
    ".tar.bz2",
    ".tgz",
    ".zip",
    ".appimage",
    ".deb",
    ".sh",
    ".run",
    ".bin",
]

KNOWN_TOKENS = [
    r"x86_64",
    r"amd64",
    r"aarch64",
    r"arm64",
    r"x64",
    r"linux",
    r"stable",
    r"latest",
    r"release",
    r"setup",
    r"installer",
    r"portable",
]


def strip_extension(filename: str) -> str:
    """Strip known compound or single extensions."""
    base = os.path.basename(filename)
    lower = base.lower()
    for ext in COMPOUND_EXTENSIONS:
        if lower.endswith(ext):
            return base[: -len(ext)]
    # Fallback to standard splitext
    return os.path.splitext(base)[0]


def derive_slug(filename: str, package_name: Optional[str] = None) -> str:
    """
    Derive a clean ASCII slug according to Section 5.1 rules.
    If package_name is given (e.g., for .deb packages), it is preferred.
    """
    if package_name and package_name.strip():
        name = package_name.strip()
    else:
        name = strip_extension(filename)

    # Convert to lowercase
    s = name.lower()

    # Remove version patterns like _1.93.1-1726079302 or -1.6.7 or 11.0.5 or v1.2.3
    # Matches version numbers separated by dots or dashes/underscores with digits
    s = re.sub(r"[-_.]v?\d+(\.\d+)+([-_]\d+)*", "", s)
    s = re.sub(r"[-_]\d{5,}", "", s)  # long build timestamps

    # Remove known platform/release tokens
    for token in KNOWN_TOKENS:
        # Match token surrounded by word boundaries, hyphens, or underscores
        s = re.sub(rf"(^|[-_.]){token}([-_.]|$)", r"\1\2", s)

    # Replace any non-alphanumeric character with hyphen
    s = re.sub(r"[^a-z0-9]+", "-", s)

    # Collapse consecutive hyphens and strip from edges
    s = re.sub(r"-+", "-", s).strip("-")

    return s


def check_conflicts(
    slug: str,
    mode: str = "system",
    user_home: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Check for naming and path conflicts as defined in Section 5.4.
    Returns a dictionary of conflict details and suggested resolutions.
    """
    home = user_home or Path.home()
    if mode == "system":
        target_dir = Path("/opt") / slug
        bin_dir = Path("/usr/local/bin")
        desktop_dir = Path("/usr/share/applications")
        manifest_path = Path("/var/lib/smart-installer") / f"{slug}.json"
    else:
        target_dir = home / ".local/opt" / slug
        bin_dir = home / ".local/bin"
        desktop_dir = home / ".local/share/applications"
        manifest_path = home / ".local/share/smart-installer/installs" / f"{slug}.json"

    bin_path = bin_dir / slug
    desktop_path = desktop_dir / f"{slug}.desktop"

    conflicts = {
        "has_conflict": False,
        "target_exists": target_dir.exists(),
        "has_manifest": manifest_path.exists(),
        "target_dir": str(target_dir),
        "bin_exists": bin_path.exists(),
        "bin_path": str(bin_path),
        "bin_points_to_target": False,
        "system_cmd_exists": False,
        "suggested_bin_name": slug,
        "desktop_exists": desktop_path.exists(),
        "desktop_is_ours": False,
        "suggested_desktop_filename": f"{slug}.desktop",
        "action_required": None,  # "upgrade", "overwrite_warning", "rename"
        "messages": [],
    }

    # 1. Target directory check
    if conflicts["target_exists"]:
        conflicts["has_conflict"] = True
        if conflicts["has_manifest"]:
            conflicts["action_required"] = "upgrade"
            conflicts["messages"].append(
                f"مجلد الهدف '{target_dir}' موجود وله سجل تثبيت سابق (يمكن الترقية والاستبدال)."
            )
        else:
            conflicts["action_required"] = "overwrite_warning"
            conflicts["messages"].append(
                f"مجلد الهدف '{target_dir}' موجود مسبقاً بدون سجل تثبيت معروف."
            )

    # 2. Binary command check
    if bin_path.exists():
        conflicts["has_conflict"] = True
        # Check if it's a symlink pointing to our target directory
        if bin_path.is_symlink():
            try:
                target_resolved = os.path.realpath(str(bin_path))
                if target_resolved.startswith(str(target_dir)):
                    conflicts["bin_points_to_target"] = True
            except Exception:
                pass

        if not conflicts["bin_points_to_target"]:
            conflicts["suggested_bin_name"] = f"{slug}-app"
            conflicts["messages"].append(
                f"أمر الطرفية '{bin_path}' موجود مسبقاً ولا يشير لمجلد البرنامج. يُقترح استخدام '{slug}-app'."
            )
    else:
        # Check if command exists anywhere in PATH
        which_path = shutil.which(slug)
        if which_path:
            conflicts["system_cmd_exists"] = True
            conflicts["has_conflict"] = True
            conflicts["suggested_bin_name"] = f"{slug}-app"
            conflicts["messages"].append(
                f"يوجد أمر نظام موجود مسبقاً باسم '{slug}' في '{which_path}'. يُقترح استخدام '{slug}-app'."
            )

    # 3. Desktop entry check
    if desktop_path.exists():
        conflicts["has_conflict"] = True
        try:
            content = desktop_path.read_text(encoding="utf-8", errors="ignore")
            if f"X-SmartInstaller-Slug={slug}" in content:
                conflicts["desktop_is_ours"] = True
            else:
                conflicts["suggested_desktop_filename"] = f"{slug}-smart.desktop"
                conflicts["messages"].append(
                    f"ملف الاختصار '{desktop_path.name}' موجود ولا يتبع المثبت الذكي. سيتم استخدام '{slug}-smart.desktop'."
                )
        except Exception:
            conflicts["suggested_desktop_filename"] = f"{slug}-smart.desktop"

    return conflicts

