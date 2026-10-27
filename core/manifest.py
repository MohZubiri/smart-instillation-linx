"""
Manifest and Uninstallation management module.
Follows rules defined in Section 5.3.
"""

import datetime
import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.desktop_entry import update_desktop_database


@dataclass
class InstallManifest:
    slug: str
    display_name: str
    mode: str  # "system" or "user"
    format: str  # "archive", "deb", "appimage", "script"
    source_file: str
    source_sha256: str
    installed_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    created_paths: List[str] = field(default_factory=list)
    deb_package: Optional[str] = None
    log_path: Optional[str] = None
    exec_cmd: Optional[str] = None
    desktop_file: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstallManifest":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def get_manifest_path(slug: str, mode: str = "user", user_home: Optional[Path] = None) -> Path:
    """Get the standard manifest file path for a given slug and mode."""
    if mode == "system":
        return Path("/var/lib/smart-installer") / f"{slug}.json"
    home = user_home or Path.home()
    return home / ".local/share/smart-installer/installs" / f"{slug}.json"


def save_user_manifest(manifest: InstallManifest, user_home: Optional[Path] = None) -> Path:
    """Save manifest for user mode installs."""
    path = get_manifest_path(manifest.slug, mode="user", user_home=user_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest.to_dict(), f, ensure_ascii=False, indent=2)
    return path


def load_manifest(slug: str, mode: Optional[str] = None) -> Optional[InstallManifest]:
    """Load manifest by slug, trying user mode and system mode if mode is not specified."""
    modes = [mode] if mode else ["user", "system"]
    for m in modes:
        path = get_manifest_path(slug, mode=m)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return InstallManifest.from_dict(data)
            except Exception:
                continue
    return None


def list_installed_manifests(user_home: Optional[Path] = None) -> List[InstallManifest]:
    """List all installed packages recorded in user and system manifest locations."""
    home = user_home or Path.home()
    manifests: List[InstallManifest] = []

    dirs = [
        home / ".local/share/smart-installer/installs",
        Path("/var/lib/smart-installer"),
    ]

    for d in dirs:
        if not d.exists():
            continue
        for p in d.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    manifests.append(InstallManifest.from_dict(data))
            except Exception:
                continue

    # Sort descending by install date
    manifests.sort(key=lambda m: m.installed_at, reverse=True)
    return manifests


def uninstall_user_package(
    manifest: InstallManifest,
    log_cb: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """
    Uninstall a package installed in user mode.
    Removes only paths recorded in manifest.
    """
    def log(msg: str):
        if log_cb:
            log_cb(msg)

    log(f"بدء إزالة البرنامج: {manifest.display_name} ({manifest.slug})")

    # Remove recorded created paths
    for p_str in manifest.created_paths:
        p = Path(p_str)
        if not p.exists() and not p.is_symlink():
            continue
        try:
            if p.is_symlink() or p.is_file():
                p.unlink()
                log(f"تم حذف الملف: {p_str}")
            elif p.is_dir():
                shutil.rmtree(p)
                log(f"تم حذف المجلد: {p_str}")
        except Exception as e:
            log(f"تحذير: تعذر حذف {p_str}: {e}")

    # Update desktop database
    desktop_dir = Path.home() / ".local/share/applications"
    if desktop_dir.exists():
        update_desktop_database(str(desktop_dir))

    # Remove manifest file
    m_path = get_manifest_path(manifest.slug, mode="user")
    if m_path.exists():
        try:
            m_path.unlink()
            log(f"تم حذف ملف السجل: {m_path}")
        except Exception as e:
            log(f"تحذير: تعذر حذف ملف السجل {m_path}: {e}")

    log("اكتملت إزالة البرنامج بنجاح.")
    return True, "تمت الإزالة بنجاح"

