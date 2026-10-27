#!/usr/bin/env python3
"""
Privileged Helper for Ubuntu Smart Package Installer.
Runs as root via pkexec to perform system-level operations safely.
Strictly whitelists allowed operations and allowed path roots.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ALLOWED_ROOTS = [
    "/opt/",
    "/usr/local/bin/",
    "/usr/share/applications/",
    "/usr/share/icons/hicolor/",
    "/var/lib/smart-installer/",
    "/tmp/",
]

ALLOWED_OPS = {
    "mkdir",
    "move_tree",
    "chown",
    "chmod",
    "symlink",
    "write_file",
    "remove",
    "apt_install_deb",
    "apt_remove",
    "run_script",
    "update_desktop_database",
    "write_manifest",
}


def send_feedback(
    step: int,
    total: int,
    pct: int,
    msg: str,
    level: str = "info",
) -> None:
    """Send JSON line feedback to stdout."""
    payload = {
        "step": step,
        "total": total,
        "pct": pct,
        "msg": msg,
        "level": level,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def is_path_allowed(path_str: str, staging_dir: Optional[str] = None) -> bool:
    """
    Verify that canonical path lies within one of the strictly allowed roots.
    Prevents path traversal or unauthorized modifications.
    Resolves parent directory to avoid following broken or external symlinks on target.
    """
    if not path_str:
        return False

    try:
        norm = os.path.normpath(os.path.abspath(path_str))
        parent_resolved = os.path.realpath(os.path.dirname(norm))
        real_p = os.path.join(parent_resolved, os.path.basename(norm))
    except Exception:
        return False

    # Check against allowed roots
    for root in ALLOWED_ROOTS:
        real_root = os.path.realpath(root)
        if real_p == real_root or real_p.startswith(real_root + os.sep) or (real_root == "/tmp" and real_p.startswith("/tmp")):
            return True

    # Check against staging dir if specified
    if staging_dir:
        real_staging = os.path.realpath(staging_dir)
        if real_p == real_staging or real_p.startswith(real_staging + os.sep) or real_p.startswith(real_staging):
            return True

    return False


def validate_batch(operations: List[Dict[str, Any]], staging_dir: Optional[str] = None) -> Optional[str]:
    """Validate all operations and paths before executing anything."""
    for i, op_data in enumerate(operations):
        op = op_data.get("op")
        args = op_data.get("args", {})

        if op not in ALLOWED_OPS:
            return f"عملية غير مسموحة: '{op}' في الخطوة {i + 1}"

        # Check paths in args
        for key in ["path", "src", "dst", "target", "link_name", "deb_path", "script_path", "dir"]:
            if key in args:
                p_val = args[key]
                if isinstance(p_val, str) and not is_path_allowed(p_val, staging_dir):
                    return f"مسار غير مصرح به: '{p_val}' في العملية '{op}' (الخطوة {i + 1})"

    return None


def execute_operation(op: str, args: Dict[str, Any]) -> None:
    """Execute a single whitelisted privileged operation."""
    if op == "mkdir":
        p = Path(args["path"])
        mode = args.get("mode", 0o755)
        p.mkdir(parents=True, exist_ok=True)
        os.chmod(str(p), mode)

    elif op == "move_tree":
        src = args["src"]
        dst = args["dst"]
        p_dst = Path(dst)
        p_dst.parent.mkdir(parents=True, exist_ok=True)
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.move(src, dst)
        # Ensure root ownership and executable permissions in destination
        try:
            if dst.startswith("/opt"):
                shutil.chown(dst, user="root", group="root")
                for root, dirs, files in os.walk(dst):
                    for d in dirs:
                        dp = os.path.join(root, d)
                        shutil.chown(dp, user="root", group="root")
                        os.chmod(dp, 0o755)
                    for f in files:
                        fp = os.path.join(root, f)
                        shutil.chown(fp, user="root", group="root")
                        # Mark binaries or scripts as executable
                        st = os.stat(fp)
                        if (st.st_mode & 0o111) or fp.endswith((".sh", ".bin")) or f == p_dst.name:
                            os.chmod(fp, 0o755)
        except Exception:
            pass

    elif op == "chown":
        p = args["path"]
        user = args.get("user", "root")
        group = args.get("group", "root")
        recursive = args.get("recursive", True)
        if recursive and os.path.isdir(p):
            shutil.chown(p, user=user, group=group)
            for root, dirs, files in os.walk(p):
                for d in dirs:
                    shutil.chown(os.path.join(root, d), user=user, group=group)
                for f in files:
                    shutil.chown(os.path.join(root, f), user=user, group=group)
        else:
            shutil.chown(p, user=user, group=group)

    elif op == "chmod":
        p = args["path"]
        mode = args["mode"]
        if isinstance(mode, str):
            mode = int(mode, 8)
        os.chmod(p, mode)

    elif op == "symlink":
        target = args["target"]
        link_name = args["link_name"]
        p_link = Path(link_name)
        p_link.parent.mkdir(parents=True, exist_ok=True)
        if os.path.islink(link_name) or os.path.exists(link_name):
            os.unlink(link_name)
        os.symlink(target, link_name)
        # Ensure target executable has execute permissions
        if os.path.exists(target):
            try:
                st = os.stat(target)
                os.chmod(target, st.st_mode | 0o755)
            except Exception:
                pass

    elif op == "write_file":
        p = Path(args["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        content = args["content"]
        mode = args.get("mode", 0o644)
        p.write_text(content, encoding="utf-8")
        os.chmod(str(p), mode)

    elif op == "remove":
        p = Path(args["path"])
        if p.is_symlink() or p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(str(p))

    elif op == "apt_install_deb":
        deb_path = args["deb_path"]
        cmd = [
            "apt-get",
            "install",
            "-y",
            "-o", "APT::Status-Fd=1",
            "-o", "Dpkg::Options::=--force-confdef",
            "-o", "Dpkg::Options::=--force-confold",
            deb_path,
        ]
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if proc.stdout:
            for line in proc.stdout:
                line = line.strip()
                if line.startswith("pmstatus:") or line.startswith("dlstatus:"):
                    # Broadcast apt status line
                    parts = line.split(":")
                    if len(parts) >= 4:
                        try:
                            pct = int(float(parts[2]))
                            send_feedback(0, 100, pct, parts[3], level="info")
                        except Exception:
                            pass
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"فشل تثبيت الحزمة عبر apt-get (رمز الخروج: {proc.returncode})")

    elif op == "apt_remove":
        pkg = args["package"]
        cmd = ["apt-get", "remove", "-y", pkg]
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"فشل إزالة الحزمة {pkg}: {proc.stderr or proc.stdout}")

    elif op == "run_script":
        script_path = args["script_path"]
        script_args = args.get("args", [])
        cwd = args.get("cwd", str(Path(script_path).parent))
        cmd = [script_path] + script_args
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"فشل تشغيل السكربت (رمز الخروج: {proc.returncode}): {proc.stderr}")

    elif op == "update_desktop_database":
        dir_p = args.get("dir", "/usr/share/applications")
        if shutil.which("update-desktop-database"):
            subprocess.run(["update-desktop-database", dir_p], capture_output=True, check=False)

    elif op == "write_manifest":
        slug = args["slug"]
        manifest_data = args["manifest_data"]
        target_file = Path("/var/lib/smart-installer") / f"{slug}.json"
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(str(target_file), 0o644)


def main():
    try:
        raw_input = sys.stdin.readline()
        if not raw_input:
            send_feedback(0, 0, 0, "لا توجد بيانات مدخلة للمساعد.", level="error")
            sys.exit(1)

        payload = json.loads(raw_input)
        staging_dir = payload.get("staging_dir")
        operations = payload.get("operations", [])

        # Validate all operations and paths before executing
        validation_error = validate_batch(operations, staging_dir)
        if validation_error:
            send_feedback(0, 0, 0, validation_error, level="error")
            sys.exit(2)

        total = len(operations)
        for i, op_data in enumerate(operations):
            op = op_data.get("op")
            args = op_data.get("args", {})
            title = op_data.get("title_ar", op)
            pct = int(((i + 1) / total) * 100) if total > 0 else 100

            send_feedback(i + 1, total, pct, f"جارٍ تنفيذ: {title}", level="info")
            try:
                execute_operation(op, args)
            except Exception as e:
                send_feedback(i + 1, total, pct, f"فشلت العملية '{op}': {e}", level="error")
                sys.exit(3)

        send_feedback(total, total, 100, "اكتملت جميع العمليات بصلاحيات الجذر بنجاح.", level="info")
        sys.exit(0)

    except Exception as e:
        send_feedback(0, 0, 0, f"خطأ غير متوقع في المساعد: {e}", level="error")
        sys.exit(4)


if __name__ == "__main__":
    main()

