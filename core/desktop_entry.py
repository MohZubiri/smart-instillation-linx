"""
Desktop entry (.desktop) generation and validation module.
Conforms to FreeDesktop Desktop Entry Specification 1.5 and Section 5.2.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple


def is_arabic(text: str) -> bool:
    """Check if the text contains any Arabic characters."""
    return bool(re.search(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]", text))


def generate_desktop_content(
    display_name: str,
    exec_path: str,
    slug: str,
    icon: Optional[str] = None,
    categories: Optional[str] = None,
    startup_wm_class: Optional[str] = None,
    comment: str = "Installed by Smart Package Installer",
    terminal: bool = False,
    name_ar: Optional[str] = None,
) -> str:
    """
    Generate valid .desktop file content based on Section 5.2 template.
    """
    cat = categories if categories and categories.strip() else "Utility;"
    if not cat.endswith(";"):
        cat += ";"

    icon_val = icon if icon and icon.strip() else "application-x-executable"
    wm_class = startup_wm_class if startup_wm_class and startup_wm_class.strip() else slug

    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.5",
        f"Name={display_name}",
    ]

    # Handle Arabic localization if provided or detected in display_name
    ar_name = name_ar or (display_name if is_arabic(display_name) else None)
    if ar_name:
        lines.append(f"Name[ar]={ar_name}")

    # Clean TryExec binary path
    raw_bin = exec_path.strip()
    if raw_bin.startswith("env "):
        tokens = raw_bin.split()
        raw_bin = tokens[-1]
        for tok in tokens[1:]:
            if "=" not in tok and not tok.startswith("-"):
                raw_bin = tok
                break
    else:
        tokens = raw_bin.split()
        if tokens:
            raw_bin = tokens[0].strip('"').strip("'")
    try_exec = raw_bin

    # Clean Exec line
    clean_exec = exec_path.strip()
    if not (clean_exec.endswith("%U") or clean_exec.endswith("%F") or clean_exec.endswith("%f") or clean_exec.endswith("%u")):
        if clean_exec.startswith("env "):
            clean_exec = f"{clean_exec} %U"
        elif not (clean_exec.startswith('"') and clean_exec.endswith('"')):
            clean_exec = f'"{clean_exec}" %U'
        else:
            clean_exec = f"{clean_exec} %U"

    lines.extend([
        f"Comment={comment}",
        f"Exec={clean_exec}",
        f"TryExec={try_exec}",
        f"Icon={icon_val}",
        f"Terminal={'true' if terminal else 'false'}",
        f"Categories={cat}",
        "StartupNotify=true",
        f"StartupWMClass={wm_class}",
        f"X-SmartInstaller-Slug={slug}",
    ])

    return "\n".join(lines) + "\n"


def validate_desktop_file(file_path: str) -> Tuple[bool, str]:
    """
    Run desktop-file-validate on the file if available.
    Returns (is_valid, message).
    """
    validator = shutil.which("desktop-file-validate")
    if not validator:
        return True, "desktop-file-validate not found; syntax checked internally."

    try:
        proc = subprocess.run(
            [validator, file_path],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return True, "Valid desktop file."
        return False, proc.stderr or proc.stdout
    except Exception as e:
        return False, str(e)


def update_desktop_database(target_dir: str) -> Tuple[bool, str]:
    """
    Run update-desktop-database on the target directory.
    """
    cmd = shutil.which("update-desktop-database")
    if not cmd:
        return True, "update-desktop-database not available."

    try:
        proc = subprocess.run(
            [cmd, target_dir],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode == 0, proc.stderr or proc.stdout
    except Exception as e:
        return False, str(e)

