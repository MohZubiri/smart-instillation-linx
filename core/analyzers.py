"""
Analyzers module: format detection, archive inspection, executable detection,
icon detection, ELF validation, ldd inspection, and script analysis.
"""

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

EXCLUDED_EXECUTABLE_NAMES = {
    "chrome-sandbox",
    "chrome_crashpad_handler",
    "crashpad_handler",
    "nacl_helper",
    "nacl_helper_bootstrap",
    "libegl.so",
    "libvulkan.so",
    "default.sfx",
}

MISSING_LIB_PACKAGE_MAP = {
    "libfuse.so.2": "libfuse2t64",
    "libnss3.so": "libnss3",
    "libgtk-3.so.0": "libgtk-3-0t64",
    "libasound.so.2": "libasound2t64",
    "libXss.so.1": "libxss1",
    "libgbm.so.1": "libgbm1",
    "libnotify.so.4": "libnotify4",
}


def detect_format(file_path: str) -> Optional[str]:
    """
    Detect the package format from filename or content.
    Returns: 'deb', 'archive', 'appimage', 'script', or None.
    """
    path = Path(file_path)
    lower = path.name.lower()

    if lower.endswith(".deb"):
        return "deb"
    if lower.endswith(".appimage"):
        return "appimage"
    if (
        lower.endswith(".tar.gz")
        or lower.endswith(".tgz")
        or lower.endswith(".tar.xz")
        or lower.endswith(".tar.bz2")
        or lower.endswith(".zip")
    ):
        return "archive"
    if lower.endswith(".sh") or lower.endswith(".run") or lower.endswith(".bin"):
        return "script"

    # Check magic bytes for archives or deb
    try:
        with open(file_path, "rb") as f:
            header = f.read(512)
            if header.startswith(b"!<arch>\ndebian-binary"):
                return "deb"
            if header.startswith(b"\x1f\x8b") or header.startswith(b"\xfd7zXZ\x00") or header.startswith(b"BZh"):
                return "archive"
            if header.startswith(b"PK\x03\x04"):
                return "archive"
            if b"AI\x02" in header[:16] or b"\x7fELF" in header[:4]:
                # Might be AppImage or script
                if b"AppImage" in header:
                    return "appimage"
    except Exception:
        pass

    return None


def inspect_archive(file_path: str) -> Dict[str, Any]:
    """
    Inspect archive before extraction without running as root.
    Checks for path traversal vulnerabilities, member count, and total uncompressed size.
    """
    result = {
        "valid": True,
        "member_count": 0,
        "uncompressed_size": 0,
        "error": None,
    }

    path = Path(file_path)
    lower = path.name.lower()

    try:
        if lower.endswith(".zip"):
            with zipfile.ZipFile(file_path, "r") as zf:
                infos = zf.infolist()
                result["member_count"] = len(infos)
                for info in infos:
                    result["uncompressed_size"] += info.file_size
                    # Path traversal checks
                    name = info.filename
                    if name.startswith("/") or name.startswith("\\"):
                        result["valid"] = False
                        result["error"] = f"مسار مطلق غير آمن في الأرشيف: {name}"
                        return result
                    parts = Path(name).parts
                    if ".." in parts:
                        result["valid"] = False
                        result["error"] = f"محاولة خروج من المجلد (..) غير آمنة: {name}"
                        return result
        else:
            with tarfile.open(file_path, "r:*") as tf:
                members = tf.getmembers()
                result["member_count"] = len(members)
                for m in members:
                    result["uncompressed_size"] += m.size
                    name = m.name
                    if name.startswith("/") or name.startswith("\\"):
                        result["valid"] = False
                        result["error"] = f"مسار مطلق غير آمن في الأرشيف: {name}"
                        return result
                    parts = Path(name).parts
                    if ".." in parts:
                        result["valid"] = False
                        result["error"] = f"محاولة خروج من المجلد (..) غير آمنة: {name}"
                        return result
                    if m.issym() or m.islnk():
                        # Symlink safety check
                        link_target = m.linkname
                        if link_target.startswith("/"):
                            # Absolute symlink target might be ok if within system, but warn
                            pass
                        elif ".." in Path(link_target).parts:
                            # Relative traversal
                            resolved = (Path(m.name).parent / link_target).resolve()
                            try:
                                resolved.relative_to(Path("."))
                            except ValueError:
                                result["valid"] = False
                                result["error"] = f"رابط رمزي يشير خارج شجرة الأرشيف: {m.name} -> {link_target}"
                                return result
    except Exception as e:
        result["valid"] = False
        result["error"] = f"تعذر قراءة ملف الأرشيف: {e}"

    return result


def is_elf_executable(file_path: Path) -> bool:
    """
    Check if a file is an ELF executable (has PT_INTERP program header or is ET_EXEC).
    Filters out shared libraries (.so).
    """
    try:
        if not file_path.is_file() or file_path.stat().st_size < 64:
            return False
        with open(file_path, "rb") as f:
            magic = f.read(4)
            if magic != b"\x7fELF":
                return False

            ei_class = f.read(1)[0]  # 1 = 32-bit, 2 = 64-bit
            ei_data = f.read(1)[0]   # 1 = LE, 2 = BE
            endian = "<" if ei_data == 1 else ">"

            # Check e_type (2 bytes at offset 16)
            f.seek(16)
            e_type = struct.unpack(f"{endian}H", f.read(2))[0]
            if e_type == 2:  # ET_EXEC
                return True

            # If ET_DYN (3), it could be PIE executable or shared library (.so)
            # Check program headers for PT_INTERP (segment type 3)
            if ei_class == 2:  # 64-bit
                f.seek(32)
                e_phoff = struct.unpack(f"{endian}Q", f.read(8))[0]
                f.seek(54)
                e_phentsize = struct.unpack(f"{endian}H", f.read(2))[0]
                e_phnum = struct.unpack(f"{endian}H", f.read(2))[0]
                for i in range(min(e_phnum, 64)):
                    f.seek(e_phoff + i * e_phentsize)
                    p_type = struct.unpack(f"{endian}I", f.read(4))[0]
                    if p_type == 3:  # PT_INTERP
                        return True
            elif ei_class == 1:  # 32-bit
                f.seek(28)
                e_phoff = struct.unpack(f"{endian}I", f.read(4))[0]
                f.seek(42)
                e_phentsize = struct.unpack(f"{endian}H", f.read(2))[0]
                e_phnum = struct.unpack(f"{endian}H", f.read(2))[0]
                for i in range(min(e_phnum, 64)):
                    f.seek(e_phoff + i * e_phentsize)
                    p_type = struct.unpack(f"{endian}I", f.read(4))[0]
                    if p_type == 3:  # PT_INTERP
                        return True
    except Exception:
        pass
    return False


ELF_MACHINE_NAMES = {
    0x03: "i386",
    0x08: "mips",
    0x14: "ppc",
    0x15: "ppc64",
    0x16: "s390x",
    0x28: "arm",
    0x3E: "x86_64",
    0xB7: "aarch64",
    0xF3: "riscv64",
}

# Architectures each host machine can execute natively
COMPATIBLE_MACHINES = {
    "x86_64": {"x86_64", "i386"},
    "aarch64": {"aarch64", "arm"},
}


def get_elf_machine(file_path: Path) -> Optional[str]:
    """Return the ELF target architecture name (e.g. 'x86_64', 'aarch64') or None if not ELF."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(20)
        if len(header) < 20 or header[:4] != b"\x7fELF":
            return None
        endian = "<" if header[5] == 1 else ">"
        e_machine = struct.unpack(f"{endian}H", header[18:20])[0]
        return ELF_MACHINE_NAMES.get(e_machine, f"unknown(0x{e_machine:x})")
    except Exception:
        return None


def check_elf_arch_compatible(file_path: Path) -> Optional[str]:
    """
    Return an error message if the ELF binary targets a different CPU architecture
    than the running system, otherwise None.
    """
    file_arch = get_elf_machine(file_path)
    if not file_arch:
        return None
    host_arch = os.uname().machine
    if file_arch in COMPATIBLE_MACHINES.get(host_arch, {host_arch}):
        return None
    return (
        f"الملف '{file_path.name}' مبني لمعمارية {file_arch} بينما جهازك يعمل بمعمارية {host_arch}، "
        f"لذلك لن يعمل. حمّل نسخة البرنامج المخصّصة لـ {host_arch} (x64/amd64)."
    )


def is_excluded_executable(name: str) -> bool:
    """Check if the binary name is an internal helper, library, or SFX module to exclude."""
    lower = name.lower()
    if lower in EXCLUDED_EXECUTABLE_NAMES:
        return True
    if lower.endswith(".sfx") or lower.endswith(".o") or lower.endswith(".a"):
        return True
    if lower in ("makefile", "license.txt", "readme.txt", "order.txt", "acknow.txt"):
        return True
    if lower.startswith("libegl") or lower.startswith("libvulkan"):
        return True
    if lower.endswith(".so") or ".so." in lower:
        return True
    if lower.endswith("_helper") or lower.endswith("crashpad_handler"):
        return True
    if lower.startswith("minidump"):
        return True
    return False


def is_gui_executable(executable_path: Path) -> bool:
    """
    Check if an executable is a GUI application or a CLI tool.
    Checks dynamic library dependencies for GUI toolkit markers.
    """
    gui_lib_markers = (
        b"libX11",
        b"libxcb",
        b"libwayland",
        b"libgtk",
        b"libgdk",
        b"libQt",
        b"libSDL",
        b"libEGL",
        b"libGL",
        b"electron",
        b"libflutter",
        b"libcef",
        b"libwx",
        b"libfltk",
    )
    # Scan the whole binary in overlapping chunks: large self-contained apps (e.g. Telegram)
    # keep these strings far beyond the first few megabytes.
    chunk_size = 8 * 1024 * 1024
    overlap = max(len(m) for m in gui_lib_markers)
    try:
        if not executable_path.is_file():
            return True
        with open(executable_path, "rb") as f:
            tail = b""
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                content = tail + chunk
                for marker in gui_lib_markers:
                    if marker in content:
                        return True
                tail = content[-overlap:]
    except Exception:
        pass
    return False


def read_bundled_desktop(desktop_path: Path) -> Dict[str, Any]:
    """Parse FreeDesktop .desktop file and extract key attributes."""
    data = {
        "name": "",
        "exec": "",
        "icon": "",
        "categories": "Utility;",
        "startup_wm_class": "",
        "mimetype": "",
    }
    if not desktop_path.exists():
        return data

    try:
        content = desktop_path.read_text(encoding="utf-8", errors="ignore")
        in_entry = False
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("["):
                in_entry = (line == "[Desktop Entry]")
                continue
            if not in_entry or "=" not in line or line.startswith("#"):
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if key == "Name" and not data["name"]:
                data["name"] = val
            elif key == "Exec" and not data["exec"]:
                data["exec"] = val
            elif key == "Icon" and not data["icon"]:
                data["icon"] = val
            elif key == "Categories" and not data["categories"]:
                data["categories"] = val
            elif key == "StartupWMClass" and not data["startup_wm_class"]:
                data["startup_wm_class"] = val
            elif key == "MimeType" and not data["mimetype"]:
                data["mimetype"] = val
    except Exception:
        pass

    return data


def detect_electron_wmclass(extracted_root: Path) -> Optional[str]:
    """Read Electron package.json to determine app name or productName."""
    candidates = [
        extracted_root / "resources/app/package.json",
        extracted_root / "package.json",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    val = data.get("productName") or data.get("name")
                    if val and isinstance(val, str):
                        return val.strip()
            except Exception:
                pass
    return None


def find_executable(extracted_root: Path, slug: str) -> Tuple[Optional[Path], List[Path]]:
    """
    Find main executable in extracted root according to Section 4-A priority.
    Returns (selected_executable_or_none, all_candidates).
    """
    candidates: List[Path] = []
    seen: Set[str] = set()

    def add_candidate(p: Path):
        key = str(p.resolve())
        if key not in seen and not is_excluded_executable(p.name):
            seen.add(key)
            candidates.append(p)

    # Priority 1: Embedded *.desktop
    desktop_files = (
        list(extracted_root.glob("*.desktop"))
        + list(extracted_root.glob("share/applications/*.desktop"))
        + list(extracted_root.glob("**/*.desktop"))
    )
    if desktop_files:
        info = read_bundled_desktop(desktop_files[0])
        exec_val = info.get("exec", "")
        if exec_val:
            raw_cmd = exec_val.split()[0].strip('"').strip("'")
            cmd_name = Path(raw_cmd).name
            target_p = extracted_root / cmd_name
            if target_p.exists() and (is_elf_executable(target_p) or os.access(target_p, os.X_OK) or target_p.suffix in (".sh", "")):
                return target_p, [target_p]
            bin_p = extracted_root / "bin" / cmd_name
            if bin_p.exists() and (is_elf_executable(bin_p) or os.access(bin_p, os.X_OK) or bin_p.suffix in (".sh", "")):
                return bin_p, [bin_p]
            # Search anywhere in extracted tree
            matches = [m for m in extracted_root.glob(f"**/{cmd_name}") if m.is_file() and not is_excluded_executable(m.name)]
            if matches:
                return matches[0], matches

    # Priority 2: File matching slug or root folder name in root or bin/
    target_names = {slug.lower(), extracted_root.name.lower()}
    for name in target_names:
        p1 = extracted_root / name
        if p1.exists() and (is_elf_executable(p1) or p1.name.endswith(".sh")):
            return p1, [p1]
        p2 = extracted_root / "bin" / name
        if p2.exists() and (is_elf_executable(p2) or p2.name.endswith(".sh")):
            return p2, [p2]

    # Priority 3: JetBrains/Android Studio launch script in bin/*.sh with shebang
    bin_dir = extracted_root / "bin"
    if bin_dir.exists() and bin_dir.is_dir():
        for sh_file in bin_dir.glob("*.sh"):
            if sh_file.name not in ("install.sh", "uninstall.sh", "setup.sh"):
                try:
                    with open(sh_file, "rb") as f:
                        if f.read(2) == b"#!":
                            return sh_file, [sh_file]
                except Exception:
                    pass

    # Priority 4: ELF executable in root with PT_INTERP
    for item in extracted_root.iterdir():
        if item.is_file() and is_elf_executable(item):
            add_candidate(item)

    # Priority 5: Scan bin/ as well
    if bin_dir.exists():
        for item in bin_dir.iterdir():
            if item.is_file() and (is_elf_executable(item) or item.suffix in (".sh", "")):
                add_candidate(item)

    if len(candidates) == 1:
        return candidates[0], candidates

    # Rank candidates by match with slug
    best_candidate = None
    best_score = -1
    slug_clean = slug.lower().replace("-", "").replace("_", "")
    for c in candidates:
        c_clean = c.stem.lower().replace("-", "").replace("_", "")
        score = 0
        if c_clean == slug_clean:
            score = 100
        elif slug_clean.startswith(c_clean) and len(c_clean) >= 2:
            score = 80 + len(c_clean)
        elif c_clean in slug_clean and len(c_clean) >= 2:
            score = 50 + len(c_clean)
        elif slug_clean in c_clean:
            score = 40
        # Deprioritize un-prefixed commands like 'unrar' when 'rar' exists
        if c_clean.startswith("un"):
            score -= 10
        if score > best_score:
            best_score = score
            best_candidate = c

    if best_candidate and best_score > 0:
        return best_candidate, candidates

    return (candidates[0] if candidates else None), candidates


def find_icon(
    extracted_root: Path,
    slug: str,
    bundled_icon_name: Optional[str] = None,
) -> Optional[Path]:
    """
    Find best icon according to Section 4-A priority:
    1. Icon specified in bundled .desktop
    2. Any .svg file
    3. Largest .png file
    """
    # 1. Bundled icon name
    if bundled_icon_name:
        # Check if direct file
        p = Path(bundled_icon_name)
        if p.is_absolute() and p.exists():
            return p
        match = list(extracted_root.glob(f"**/{bundled_icon_name}*"))
        for m in match:
            if m.is_file() and m.suffix in (".svg", ".png"):
                return m

    # 2. .svg file in root, bin/, resources/, share/
    svg_files = (
        list(extracted_root.glob("*.svg"))
        + list(extracted_root.glob("bin/*.svg"))
        + list(extracted_root.glob("resources/*.svg"))
        + list(extracted_root.glob("share/icons/**/*.svg"))
    )
    if svg_files:
        # Prioritize one matching slug
        for s in svg_files:
            if slug in s.name.lower():
                return s
        return svg_files[0]

    # 3. Largest .png
    png_files = (
        list(extracted_root.glob("*.png"))
        + list(extracted_root.glob("bin/*.png"))
        + list(extracted_root.glob("resources/*.png"))
        + list(extracted_root.glob("share/icons/**/*.png"))
    )
    if png_files:
        png_files.sort(key=lambda p: p.stat().st_size if p.is_file() else 0, reverse=True)
        return png_files[0]

    return None


def ldd_check(executable_path: str) -> List[Tuple[str, str]]:
    """
    Run ldd on the executable and identify missing libraries.
    Returns list of tuples: [(missing_library_so, suggested_package_name), ...]
    """
    ldd = shutil.which("ldd")
    if not ldd or not Path(executable_path).exists():
        return []

    missing: List[Tuple[str, str]] = []
    try:
        proc = subprocess.run(
            [ldd, executable_path],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        for line in proc.stdout.splitlines():
            if "not found" in line:
                parts = line.strip().split("=>")
                lib_name = parts[0].strip()
                suggested_pkg = MISSING_LIB_PACKAGE_MAP.get(lib_name, "lib...")
                missing.append((lib_name, suggested_pkg))
    except Exception:
        pass

    return missing


def detect_filesystem_type(file_path: str) -> str:
    """Detect filesystem type of source file using findmnt."""
    cmd = shutil.which("findmnt")
    if not cmd or not os.path.exists(file_path):
        return "unknown"
    try:
        proc = subprocess.run(
            [cmd, "-no", "FSTYPE", "--target", file_path],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.stdout.strip().lower()
    except Exception:
        return "unknown"


def check_fuse2_available() -> bool:
    """Check if libfuse.so.2 is available on the system."""
    cmd = shutil.which("ldconfig")
    if not cmd:
        # Check standard library paths directly
        for p in ["/lib/x86_64-linux-gnu/libfuse.so.2", "/usr/lib/libfuse.so.2", "/lib/libfuse.so.2"]:
            if os.path.exists(p):
                return True
        return False
    try:
        proc = subprocess.run(
            [cmd, "-p"],
            capture_output=True,
            text=True,
            check=False,
        )
        return "libfuse.so.2" in proc.stdout
    except Exception:
        return False


def check_apparmor_userns_restricted() -> bool:
    """Check if Ubuntu 24.04 unprivileged user namespace restriction is active."""
    path = Path("/proc/sys/kernel/apparmor_restrict_unprivileged_userns")
    if path.exists():
        try:
            return path.read_text().strip() == "1"
        except Exception:
            return False
    return False


def preview_script(file_path: str) -> Dict[str, Any]:
    """
    Generate preview information for .sh / .run / .bin scripts.
    Reads size, SHA256, first 40 lines, and checks for Makeself package.
    """
    path = Path(file_path)
    res: Dict[str, Any] = {
        "size": path.stat().st_size if path.exists() else 0,
        "sha256": "",
        "first_lines": [],
        "is_makeself": False,
        "makeself_info": "",
        "makeself_list": "",
        "contains_sudo": False,
    }

    if not path.exists():
        return res

    # Compute sha256
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    res["sha256"] = h.hexdigest()

    # Read first lines and check for makeself
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
            if b"Makeself" in head:
                res["is_makeself"] = True

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [f.readline() for _ in range(40)]
            res["first_lines"] = [line.rstrip() for line in lines if line]
            full_head = "".join(lines)
            if "sudo" in full_head or "/opt" in full_head or "/usr" in full_head:
                res["contains_sudo"] = True
    except Exception:
        pass

    # If makeself, try running with --info and --list
    if res["is_makeself"]:
        try:
            p1 = subprocess.run([file_path, "--info"], capture_output=True, text=True, timeout=3)
            res["makeself_info"] = p1.stdout or p1.stderr
            p2 = subprocess.run([file_path, "--list"], capture_output=True, text=True, timeout=3)
            res["makeself_list"] = p2.stdout or p2.stderr
        except Exception:
            pass

    return res


def read_deb_info(deb_path: str) -> Dict[str, Any]:
    """Read .deb control fields and inspect for desktop files."""
    info: Dict[str, Any] = {
        "package": "",
        "version": "",
        "architecture": "",
        "description": "",
        "depends": "",
        "desktop_file": None,
    }
    dpkg_deb = shutil.which("dpkg-deb")
    if not dpkg_deb or not os.path.exists(deb_path):
        return info

    try:
        proc = subprocess.run(
            [dpkg_deb, "-f", deb_path, "Package", "Version", "Architecture", "Description", "Depends"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in proc.stdout.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip().lower()
                v = v.strip()
                if k in info:
                    info[k] = v

        # Check for desktop files inside package
        proc_c = subprocess.run(
            [dpkg_deb, "-c", deb_path],
            capture_output=True,
            text=True,
            check=False,
        )
        desktop_candidates: List[str] = []
        for line in proc_c.stdout.splitlines():
            if "usr/share/applications/" in line and line.strip().endswith(".desktop"):
                parts = line.strip().split()
                if parts:
                    desktop_candidates.append("/" + parts[-1].strip().lstrip(".").lstrip("/"))

        # Skip helper entries (URL/MIME handlers are NoDisplay) and prefer one matching the package name
        def desktop_rank(path: str) -> int:
            stem = Path(path).stem.lower()
            if "urlhandler" in stem.replace("-", "").replace("_", "") or "handler" in stem:
                return 2
            pkg = info["package"].lower()
            return 0 if pkg and (stem == pkg or stem.endswith("." + pkg) or pkg in stem) else 1

        if desktop_candidates:
            info["desktop_file"] = min(desktop_candidates, key=desktop_rank)
    except Exception:
        pass

    return info
