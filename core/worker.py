"""
Worker thread module.
Executes the Plan step-by-step, coordinates privileged operations, handles cancellation,
streams progress, and executes automatic rollback upon failure.
"""

import datetime
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from PyQt6.QtCore import QThread, pyqtSignal
    HAVE_QT = True
except ImportError:
    HAVE_QT = False
    # Fallback dummy class for non-Qt environments
    class QThread:  # type: ignore
        def __init__(self):
            pass
        def start(self):
            self.run()

from core.analyzers import (
    check_elf_arch_compatible,
    detect_electron_wmclass,
    find_executable,
    find_icon,
    is_elf_executable,
    is_gui_executable,
    ldd_check,
    read_bundled_desktop,
)
from core.desktop_entry import generate_desktop_content, update_desktop_database, validate_desktop_file
from core.manifest import InstallManifest, save_user_manifest
from core.plan import Plan, Step, execute_rollback
from core.privileges import run_privileged_operations
from handlers.archive import extract_archive_safely, flatten_extracted_tree
from i18n import t


class InstallWorker(QThread):
    """
    Worker thread that executes an installation Plan step-by-step.
    Emits signals for UI progress, logs, and completion.
    """
    if HAVE_QT:
        progress_signal = pyqtSignal(int, str)
        log_signal = pyqtSignal(str)
        step_started_signal = pyqtSignal(str)
        finished_signal = pyqtSignal(bool, str, dict)
    else:
        # Non-Qt callback holders
        progress_signal = None  # type: ignore
        log_signal = None  # type: ignore
        step_started_signal = None  # type: ignore
        finished_signal = None  # type: ignore

    def __init__(
        self,
        plan: Plan,
        log_cb: Optional[Callable[[str], None]] = None,
        progress_cb: Optional[Callable[[int, str], None]] = None,
        parent: Optional[Any] = None,
    ):
        if HAVE_QT:
            super().__init__(parent)
        self.plan = plan
        self.custom_log_cb = log_cb
        self.custom_progress_cb = progress_cb
        self.is_cancelled = False
        self.current_process: Optional[subprocess.Popen] = None
        self.completed_steps: List[Step] = []
        self.detected_executable: Optional[Path] = None
        self.detected_icon: Optional[Path] = None
        self.log_file_path: Optional[Path] = None
        self.result_data: Dict[str, Any] = {}

    def emit_log(self, msg: str) -> None:
        """Emit log to UI signal, callback, and log file."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {msg}"
        if HAVE_QT and hasattr(self, "log_signal"):
            self.log_signal.emit(formatted)
        if self.custom_log_cb:
            self.custom_log_cb(formatted)
        if self.log_file_path:
            try:
                with open(self.log_file_path, "a", encoding="utf-8") as f:
                    f.write(formatted + "\n")
            except Exception:
                pass

    def emit_progress(self, pct: int, msg: str) -> None:
        """Emit progress update."""
        if HAVE_QT and hasattr(self, "progress_signal"):
            self.progress_signal.emit(pct, msg)
        if self.custom_progress_cb:
            self.custom_progress_cb(pct, msg)

    def cancel(self) -> None:
        """Cancel current execution and trigger rollback."""
        self.is_cancelled = True
        self.emit_log("تلقي طلب إلغاء التثبيت...")
        if self.current_process and self.current_process.poll() is None:
            try:
                self.current_process.send_signal(signal.SIGTERM)
                # Wait up to 10 seconds before SIGKILL
                for _ in range(20):
                    if self.current_process.poll() is not None:
                        break
                    time.sleep(0.5)
                if self.current_process.poll() is None:
                    self.current_process.kill()
            except Exception as e:
                self.emit_log(f"تنبيه أثناء إيقاف العملية: {e}")

    def run(self) -> None:
        """Main execution loop for all steps in the plan."""
        # Initialize log file
        log_dir = Path.home() / ".local/share/smart-installer/logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        self.log_file_path = log_dir / f"{ts}-{self.plan.slug}.log"
        self.emit_log(f"بدء عملية التثبيت لحزمة: {self.plan.display_name} ({self.plan.slug})")
        self.emit_log(f"وضع التثبيت: {self.plan.mode} | الصيغة: {self.plan.format_type}")

        total_weight = self.plan.total_weight or 100
        accumulated_weight = 0

        try:
            # Group root steps if applicable or execute sequentially
            # First check single instance lock
            lock_dir = Path.home() / ".cache/smart-installer"
            lock_dir.mkdir(parents=True, exist_ok=True)
            lock_path = lock_dir / "lock"
            
            i = 0
            steps = self.plan.steps
            while i < len(steps):
                if self.is_cancelled:
                    raise InterruptedError("تم إلغاء التثبيت بواسطة المستخدم")

                step = steps[i]
                if HAVE_QT and hasattr(self, "step_started_signal"):
                    self.step_started_signal.emit(step.title_ar)

                self.emit_log(f"خطوة [{i + 1}/{len(steps)}]: {step.title_ar}")

                # Check if this and following steps need root
                if step.needs_root and step.op not in ("run_script_step",):
                    # Gather all consecutive root steps to execute in one pkexec batch
                    root_batch = []
                    batch_weight = 0
                    j = i
                    while j < len(steps) and steps[j].needs_root and steps[j].op not in ("run_script_step",):
                        r_step = steps[j]
                        # Prepare operation dict for helper
                        op_dict = self._convert_step_to_helper_op(r_step)
                        if op_dict:
                            root_batch.append(op_dict)
                        batch_weight += r_step.weight
                        j += 1

                    if root_batch:
                        self.emit_log(f"تنفيذ مجموعة عمليات الجذر ({len(root_batch)} عمليات)...")
                        ok, msg = run_privileged_operations(
                            root_batch,
                            staging_dir=self.plan.staging_dir,
                            log_cb=self.emit_log,
                        )
                        if not ok:
                            raise RuntimeError(f"فشلت عمليات الجذر: {msg}")

                        # Mark steps as completed
                        for k in range(i, j):
                            self.completed_steps.append(steps[k])
                        accumulated_weight += batch_weight
                        pct = int((accumulated_weight / total_weight) * 100)
                        self.emit_progress(min(pct, 100), "اكتملت عمليات الجذر")
                        i = j
                        continue

                # Normal user-space or standalone step
                self._execute_step(step)
                self.completed_steps.append(step)
                accumulated_weight += step.weight
                pct = int((accumulated_weight / total_weight) * 100)
                self.emit_progress(min(pct, 100), step.title_ar)
                i += 1

            # Perform post-install checks (e.g. ldd check)
            self._post_install_inspection()

            self.emit_log("اكتملت جميع خطوات التثبيت بنجاح!")
            self.emit_progress(100, t("install_success"))
            if HAVE_QT and hasattr(self, "finished_signal"):
                self.finished_signal.emit(True, t("install_success"), self.result_data)

        except Exception as e:
            err_msg = str(e)
            self.emit_log(f"خطأ أثناء التثبيت: {err_msg}")
            # Rollback
            execute_rollback(
                self.completed_steps,
                staging_dir=self.plan.staging_dir,
                log_cb=self.emit_log,
            )
            final_msg = t("install_cancelled") if self.is_cancelled else f"{t('install_failed')}\n{err_msg}"
            self.emit_progress(0, final_msg)
            if HAVE_QT and hasattr(self, "finished_signal"):
                self.finished_signal.emit(False, final_msg, {})

    def _resolve_target_path(self, staging_path: Optional[Path], target_dir: str) -> Path:
        """Map a path from staging_dir to target_dir."""
        if not staging_path:
            return Path(target_dir)
        staging = Path(self.plan.staging_dir) if self.plan.staging_dir else None
        if staging:
            try:
                rel = staging_path.relative_to(staging)
                return Path(target_dir) / rel
            except ValueError:
                pass
        return Path(target_dir) / staging_path.name

    def _convert_step_to_helper_op(self, step: Step) -> Optional[Dict[str, Any]]:
        """Convert a Plan Step to privileged_helper JSON operation."""
        op = step.op
        args = step.args

        if op == "move_tree":
            return {"op": "move_tree", "args": {"src": args["src"], "dst": args["dst"]}, "title_ar": step.title_ar}
        elif op == "fix_chrome_sandbox":
            target_sandbox = os.path.join(args["target_dir"], "chrome-sandbox")
            staging = Path(self.plan.staging_dir) if self.plan.staging_dir else None
            # Check if chrome-sandbox exists in staging before moving, or already in target
            if (staging and (staging / "chrome-sandbox").exists()) or os.path.exists(target_sandbox):
                return {"op": "chmod", "args": {"path": target_sandbox, "mode": 0o4755}, "title_ar": step.title_ar}
            return None
        elif op == "create_symlink":
            target_dir = args.get("target_dir", "")
            if args.get("target"):
                target_exe = Path(args["target"])
            elif self.detected_executable and target_dir:
                target_exe = self._resolve_target_path(self.detected_executable, target_dir)
            else:
                target_exe = Path(target_dir) / args.get("slug", "")
            return {"op": "symlink", "args": {"target": str(target_exe), "link_name": args["link_name"]}, "title_ar": step.title_ar}
        elif op == "create_desktop_entry":
            if self._is_cli_tool(args.get("target_dir", "")):
                return None
            content = self._build_desktop_content(args)
            return {"op": "write_file", "args": {"path": args["desktop_file"], "content": content, "mode": 0o644}, "title_ar": step.title_ar}
        elif op == "update_desktop_database":
            return {"op": "update_desktop_database", "args": {"dir": args["dir"]}, "title_ar": step.title_ar}
        elif op == "apt_install_deb":
            return {"op": "apt_install_deb", "args": {"deb_path": args["deb_path"]}, "title_ar": step.title_ar}
        elif op == "write_manifest":
            manifest = self._build_manifest(args)
            return {"op": "write_manifest", "args": {"slug": args["slug"], "manifest_data": manifest.to_dict()}, "title_ar": step.title_ar}
        elif op == "copy_and_chmod":
            return {"op": "write_file", "args": {"path": args["dst_file"], "content": Path(args["src"]).read_text(errors="ignore"), "mode": args.get("mode", 0o755)}, "title_ar": step.title_ar}

        return None

    def _execute_step(self, step: Step) -> None:
        """Execute a user-space step directly."""
        op = step.op
        args = step.args

        if op == "extract_archive":
            extract_archive_safely(
                args["source"],
                args["target"],
                progress_cb=lambda p, m: self.emit_progress(p, m),
            )
            # Flatten staging directory if nested
            flatten_extracted_tree(Path(args["target"]))

        elif op == "inspect_staging":
            staging_root = Path(args["staging_dir"])
            slug = args["slug"]
            exe, candidates = find_executable(staging_root, slug)
            self.detected_executable = exe
            if exe:
                self.emit_log(f"تم اكتشاف الملف التنفيذي: {exe.name}")
                arch_error = check_elf_arch_compatible(exe)
                if arch_error:
                    raise RuntimeError(arch_error)
            else:
                self.emit_log("تحذير: لم يتم اكتشاف ملف تنفيذي مباشر.")

            icon = find_icon(staging_root, slug)
            self.detected_icon = icon
            if icon:
                self.emit_log(f"تم اكتشاف أيقونة التطبيق: {icon.name}")

        elif op == "copy_deb_to_tmp":
            dst_dir = Path(args["dst_dir"])
            dst_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(str(dst_dir), 0o755)
            shutil.copy2(args["src"], args["dst_file"])
            os.chmod(args["dst_file"], 0o644)

        elif op == "cleanup_tmp":
            if os.path.exists(args["path"]):
                shutil.rmtree(args["path"], ignore_errors=True)

        elif op == "move_tree" and not step.needs_root:
            src = args["src"]
            dst = args["dst"]
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.move(src, dst)

        elif op == "copy_and_chmod" and not step.needs_root:
            dst_dir = Path(args["dst_dir"])
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(args["src"], args["dst_file"])
            os.chmod(args["dst_file"], args.get("mode", 0o755))

        elif op == "extract_appimage_metadata":
            from handlers.appimage import extract_appimage_metadata
            meta = extract_appimage_metadata(Path(args["appimage_path"]), Path(args["staging_dir"]))
            icon_file = meta.get("icon_file")
            if icon_file and os.path.exists(icon_file):
                target_icon = Path(args["target_icon"])
                target_icon.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(icon_file, str(target_icon))
                self.detected_icon = target_icon

        elif op == "create_symlink" and not step.needs_root:
            target_dir = args.get("target_dir", "")
            if args.get("target"):
                target_exe = Path(args["target"])
            elif self.detected_executable and target_dir:
                target_exe = self._resolve_target_path(self.detected_executable, target_dir)
            else:
                target_exe = self.detected_executable or (Path(target_dir) / args.get("slug", ""))

            link_name = Path(args["link_name"])
            link_name.parent.mkdir(parents=True, exist_ok=True)
            if link_name.is_symlink() or link_name.exists():
                link_name.unlink()
            os.symlink(str(target_exe), str(link_name))
            if target_exe and target_exe.exists():
                try:
                    st = os.stat(target_exe)
                    os.chmod(target_exe, st.st_mode | 0o755)
                except Exception:
                    pass

        elif op == "create_desktop_entry" and not step.needs_root:
            if self._is_cli_tool(args.get("target_dir", "")):
                self.emit_log("البرنامج أداة طرفية بدون واجهة رسومية، لن يُنشأ اختصار في قائمة التطبيقات.")
                return
            content = self._build_desktop_content(args)
            p = Path(args["desktop_file"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            os.chmod(str(p), 0o644)
            validate_desktop_file(str(p))

        elif op == "update_desktop_database" and not step.needs_root:
            update_desktop_database(args["dir"])

        elif op == "write_manifest" and not step.needs_root:
            manifest = self._build_manifest(args)
            save_user_manifest(manifest)

        elif op == "run_script_step":
            self._execute_script_step(args)

    def _execute_script_step(self, args: Dict[str, Any]) -> None:
        """Execute script in terminal or internal log."""
        script_path = args["script_path"]
        script_args = args.get("args", [])
        run_in_terminal = args.get("run_in_terminal", True)
        run_as_root = args.get("run_as_root", False)
        cwd = args.get("cwd", str(Path(script_path).parent))

        if run_in_terminal:
            term = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal") or shutil.which("xterm")
            if not term:
                term = "x-terminal-emulator"

            cmd_str = f'"{script_path}" ' + " ".join(f'"{a}"' for a in script_args)
            bash_cmd = f'{cmd_str}; echo; read -rp "اضغط Enter للإغلاق"'
            if run_as_root:
                full_cmd = ["pkexec", term, "-e", "bash", "-c", bash_cmd]
            else:
                full_cmd = [term, "-e", "bash", "-c", bash_cmd]

            self.emit_log(f"فتح الطرفية لتشغيل السكربت: {term}")
            proc = subprocess.Popen(full_cmd, cwd=cwd)
            self.current_process = proc
            proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(f"انتهى تشغيل السكربت برمز خطأ: {proc.returncode}")
        else:
            cmd = ([ "pkexec" ] if run_as_root else []) + [script_path] + script_args
            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self.current_process = proc
            last_out_time = time.time()
            if proc.stdout:
                for line in proc.stdout:
                    line = line.strip()
                    if line:
                        self.emit_log(line)
                        last_out_time = time.time()
                    if time.time() - last_out_time > 180:
                        self.emit_log("تحذير: لا توجد مخرجات منذ 3 دقائق. يبدو أن السكربت ينتظر إدخالاً.")
            proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(f"انتهى تشغيل السكربت برمز خطأ: {proc.returncode}")

    def _locate_executable(self, target_dir: str = "") -> Optional[Path]:
        """Detected executable, looked up in staging or (after move_tree) in target_dir."""
        exe = self.detected_executable
        if not exe:
            return None
        if exe.exists():
            return exe
        if target_dir:
            moved = self._resolve_target_path(exe, target_dir)
            if moved.exists():
                return moved
        return None

    def _is_cli_tool(self, target_dir: str = "") -> bool:
        """True when the detected executable is a terminal-only ELF tool (no GUI toolkit linked)."""
        exe = self._locate_executable(target_dir)
        if not exe or exe.suffix == ".sh":
            return False
        return is_elf_executable(exe) and not is_gui_executable(exe)

    def _build_desktop_content(self, args: Dict[str, Any]) -> str:
        """Construct FreeDesktop .desktop content."""
        display_name = args.get("display_name", self.plan.display_name)
        slug = args.get("slug", self.plan.slug)
        target_dir = args.get("target_dir", "")

        exec_cmd = args.get("exec_cmd")
        if not exec_cmd:
            if self.detected_executable and target_dir:
                exec_cmd = str(self._resolve_target_path(self.detected_executable, target_dir))
            else:
                exe_name = self.detected_executable.name if self.detected_executable else slug
                exec_path = os.path.join(target_dir, exe_name)
                exec_cmd = exec_path

        icon_path = args.get("icon")
        if not icon_path:
            if self.detected_icon and target_dir:
                icon_path = str(self._resolve_target_path(self.detected_icon, target_dir))
            elif self.detected_icon:
                icon_path = str(self.detected_icon)

        # Detect Electron WMClass if applicable
        wm_class = slug
        staging = Path(self.plan.staging_dir) if self.plan.staging_dir else None
        if staging and staging.exists():
            detected_wm = detect_electron_wmclass(staging)
            if detected_wm:
                wm_class = detected_wm
        elif target_dir and os.path.exists(target_dir):
            detected_wm = detect_electron_wmclass(Path(target_dir))
            if detected_wm:
                wm_class = detected_wm

        # Detect if application is CLI/terminal-based or GUI
        exe = self._locate_executable(target_dir)
        is_term = bool(exe) and not is_gui_executable(exe)

        return generate_desktop_content(
            display_name=display_name,
            exec_path=exec_cmd,
            slug=slug,
            icon=icon_path,
            startup_wm_class=wm_class,
            terminal=is_term,
        )

    def _build_manifest(self, args: Dict[str, Any]) -> InstallManifest:
        """Construct InstallManifest dataclass."""
        meta = self.plan.metadata
        return InstallManifest(
            slug=args.get("slug", self.plan.slug),
            display_name=args.get("display_name", self.plan.display_name),
            mode=args.get("mode", self.plan.mode),
            format=args.get("format", self.plan.format_type),
            source_file=args.get("source_file", self.plan.source_file),
            source_sha256="",
            created_paths=args.get("created_paths", []),
            deb_package=args.get("deb_package", meta.get("package_name")),
            log_path=str(self.log_file_path) if self.log_file_path else None,
            exec_cmd=meta.get("bin_link"),
            desktop_file=meta.get("desktop_file"),
        )

    def _post_install_inspection(self) -> None:
        """Perform post-install inspection such as missing libraries check via ldd."""
        meta = self.plan.metadata
        target_dir = meta.get("target_dir", "")

        # Remap detected_executable path from staging to actual target_dir
        exe_in_target = None
        if self.detected_executable and target_dir:
            exe_name = self.detected_executable.name
            candidate = Path(target_dir) / exe_name
            if candidate.exists():
                exe_in_target = candidate
            else:
                # Try finding it relative to target dir structure
                staging = Path(self.plan.staging_dir) if self.plan.staging_dir else None
                if staging and self.detected_executable.is_relative_to(staging):
                    rel_path = self.detected_executable.relative_to(staging)
                    candidate = Path(target_dir) / rel_path
                    if candidate.exists():
                        exe_in_target = candidate

        bin_cmd = meta.get("bin_link", self.plan.slug)
        is_term = False
        if exe_in_target and Path(exe_in_target).exists():
            is_term = not is_gui_executable(Path(exe_in_target))
        elif self.detected_executable and self.detected_executable.exists():
            is_term = not is_gui_executable(self.detected_executable)

        self.result_data = {
            "slug": self.plan.slug,
            "display_name": self.plan.display_name,
            "bin_cmd": bin_cmd,
            "desktop_file": meta.get("desktop_file"),
            "target_dir": target_dir,
            "target_appimage_path": meta.get("target_appimage_path"),
            "exe_in_target": str(exe_in_target) if exe_in_target else "",
            "is_terminal": is_term,
            "log_path": str(self.log_file_path) if self.log_file_path else "",
            "missing_libs": [],
        }

        # Check ldd on the executable in the actual target directory
        exe_to_check = exe_in_target or (Path(bin_cmd) if bin_cmd and Path(bin_cmd).exists() else None)
        if exe_to_check and exe_to_check.exists():
            missing = ldd_check(str(exe_to_check))
            if missing:
                self.result_data["missing_libs"] = missing
                for lib, pkg in missing:
                    self.emit_log(f"تنبيه مكتبة ناقصة: {lib} (الحزمة المقترحة: {pkg})")

