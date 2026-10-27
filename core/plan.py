"""
Plan -> Execute architecture module.
Defines Step, Plan, and execution / rollback structures according to Section 2.2.
"""

import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from i18n import t


@dataclass
class Step:
    id: str
    title_ar: str
    needs_root: bool
    weight: int
    op: str
    args: Dict[str, Any] = field(default_factory=dict)
    rollback_op: str = ""
    rollback_args: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Plan:
    slug: str
    display_name: str
    mode: str  # "system" or "user"
    format_type: str  # "archive", "deb", "appimage", "script"
    source_file: str
    steps: List[Step] = field(default_factory=list)
    staging_dir: Optional[str] = None
    total_weight: int = 0
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.total_weight:
            self.total_weight = sum(s.weight for s in self.steps)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["steps"] = [s.to_dict() for s in self.steps]
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def build_plan(file_path: str, options: Optional[Dict[str, Any]] = None) -> Plan:
    """
    Build installation plan for given file and user options.
    Dispatches to appropriate handler based on detected format.
    """
    opts = options or {}
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    from core.analyzers import detect_format
    fmt = detect_format(str(path))
    if not fmt:
        raise ValueError(f"صيغة الملف غير مدعومة أو غير معروفة: {path.name}")

    if fmt == "archive":
        from handlers.archive import build_archive_plan
        return build_archive_plan(str(path), opts)
    elif fmt == "deb":
        from handlers.deb import build_deb_plan
        return build_deb_plan(str(path), opts)
    elif fmt == "appimage":
        from handlers.appimage import build_appimage_plan
        return build_appimage_plan(str(path), opts)
    elif fmt == "script":
        from handlers.script import build_script_plan
        return build_script_plan(str(path), opts)
    else:
        raise ValueError(f"Unknown format type: {fmt}")


def execute_rollback(
    completed_steps: List[Step],
    staging_dir: Optional[str] = None,
    log_cb: Optional[Callable[[str], None]] = None,
) -> None:
    """
    Execute rollback operations in reverse order for completed steps.
    Ensures no half-installed files or broken links remain.
    """
    def log(msg: str):
        if log_cb:
            log_cb(msg)

    log("بدء عملية التراجع (Rollback)...")

    for step in reversed(completed_steps):
        rb_op = step.rollback_op
        rb_args = step.rollback_args or {}
        if not rb_op:
            continue

        try:
            if rb_op == "remove":
                path_str = rb_args.get("path")
                if path_str:
                    p = Path(path_str)
                    if p.is_symlink() or p.is_file():
                        p.unlink()
                        log(f"تراجع: تم حذف {path_str}")
                    elif p.is_dir():
                        shutil.rmtree(p)
                        log(f"تراجع: تم حذف المجلد {path_str}")
            elif rb_op == "rmdir":
                path_str = rb_args.get("path")
                if path_str and Path(path_str).exists():
                    shutil.rmtree(path_str)
                    log(f"تراجع: تم حذف المجلد {path_str}")
        except Exception as e:
            log(f"خطأ أثناء التراجع عن الخطوة {step.id}: {e}")

    # Clean staging directory if any
    if staging_dir and os.path.exists(staging_dir):
        try:
            shutil.rmtree(staging_dir)
            log(f"تم تنظيف مجلد التحضير: {staging_dir}")
        except Exception as e:
            log(f"خطأ أثناء تنظيف مجلد التحضير: {e}")

    log("اكتملت عملية التراجع بنجاح.")

