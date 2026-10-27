"""
Privileged execution management module.
Coordinates running privileged_helper.py via pkexec (or fallback sudo -A).
No passwords touch the GUI or logs directly.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


def get_helper_path() -> Path:
    """
    Locate privileged_helper.py. Prefers local workspace helper if running from
    development directory, otherwise system installed path.
    """
    local_path = Path(__file__).resolve().parent.parent / "privileged_helper.py"
    sys_path = Path("/opt/smart-installer/privileged_helper.py")

    # If running from local workspace and local helper exists, use it
    if local_path.exists():
        if not str(Path(__file__).resolve()).startswith("/opt/smart-installer"):
            return local_path

    if sys_path.exists():
        return sys_path

    return local_path


def run_privileged_operations(
    operations: List[Dict[str, Any]],
    staging_dir: Optional[str] = None,
    feedback_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """
    Execute batch of privileged operations via privileged_helper.py using pkexec.
    Streams progress JSON messages to feedback_cb.
    """
    helper_path = get_helper_path()
    if not helper_path.exists():
        return False, f"ملف المساعد المتميز غير موجود: {helper_path}"

    # Determine command: pkexec /usr/bin/python3 <helper_path>
    pkexec = shutil.which("pkexec")
    python_bin = sys.executable or "/usr/bin/python3"

    if pkexec:
        cmd = [pkexec, python_bin, str(helper_path)]
    else:
        # Fallback to sudo -A if pkexec is not present
        sudo = shutil.which("sudo")
        if not sudo:
            return False, "لا توجد أداة pkexec أو sudo في النظام لتنفيذ العمليات بصلاحيات الجذر."
        cmd = [sudo, "-A", python_bin, str(helper_path)]

    payload = {
        "staging_dir": staging_dir,
        "operations": operations,
    }
    input_data = json.dumps(payload, ensure_ascii=False) + "\n"

    try:
        if log_cb:
            log_cb(f"تشغيل المساعد بصلاحيات الجذر عبر {cmd[0]}...")

        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        # Write stdin
        if proc.stdin:
            proc.stdin.write(input_data)
            proc.stdin.flush()
            proc.stdin.close()

        last_error = ""
        if proc.stdout:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if feedback_cb:
                        feedback_cb(data)
                    if log_cb and "msg" in data:
                        log_cb(data["msg"])
                    if data.get("level") == "error":
                        last_error = data.get("msg", "")
                except Exception:
                    if log_cb:
                        log_cb(line)

        proc.wait()
        stderr_output = proc.stderr.read() if proc.stderr else ""

        if proc.returncode == 0:
            return True, "تمت العمليات بنجاح"
        else:
            err_msg = last_error or stderr_output or f"فشل المساعد (رمز الخروج: {proc.returncode})"
            if "not authorized" in err_msg.lower() or proc.returncode == 126:
                err_msg = "تم إلغاء طلب الصلاحيات من قِبل المستخدم."
            return False, err_msg

    except Exception as e:
        return False, f"تعذر تشغيل المساعد: {e}"

