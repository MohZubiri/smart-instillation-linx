"""
Main window module.
Assembles the complete user interface: drag-and-drop file selection,
package info card, real-time slug validation, execution plan, progress bar,
operations log, and result screen.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from PyQt6.QtCore import Qt, QUrl
    from PyQt6.QtGui import QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QFont, QGuiApplication, QIcon
    from PyQt6.QtWidgets import (
        QButtonGroup,
        QCheckBox,
        QFileDialog,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QRadioButton,
        QScrollArea,
        QSplitter,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    pass

from core.analyzers import detect_format
from core.plan import Plan, build_plan
from core.slug import check_conflicts, derive_slug
from core.worker import InstallWorker
from i18n import t
from ui.dialogs import DoctorDialog
from ui.installed_view import InstalledView

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #1e1f29;
    color: #f8f8f2;
    font-family: 'Noto Sans Arabic', 'Ubuntu', 'Segoe UI', sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #44475a;
    background: #1e1f29;
}
QTabBar::tab {
    background: #282a36;
    color: #f8f8f2;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #6272a4;
    font-weight: bold;
}
QGroupBox {
    border: 1px solid #44475a;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top right;
    padding: 0 5px;
    color: #bd93f9;
}
QLineEdit {
    background-color: #282a36;
    border: 1px solid #6272a4;
    border-radius: 4px;
    padding: 6px;
    color: #f8f8f2;
}
QLineEdit:focus {
    border: 1px solid #bd93f9;
}
QPushButton {
    background-color: #6272a4;
    border: none;
    border-radius: 4px;
    color: #f8f8f2;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #7283b5;
}
QPushButton:pressed {
    background-color: #44475a;
}
QPushButton:disabled {
    background-color: #3b3d4f;
    color: #6272a4;
}
QProgressBar {
    border: 1px solid #44475a;
    border-radius: 5px;
    text-align: center;
    background-color: #282a36;
    color: #f8f8f2;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: #50fa7b;
    border-radius: 4px;
}
QTextEdit {
    background-color: #21222c;
    border: 1px solid #44475a;
    border-radius: 4px;
    color: #50fa7b;
    font-family: 'DejaVu Sans Mono', 'Ubuntu Mono', 'Courier New', monospace;
    font-size: 12px;
}
QTableWidget {
    background-color: #282a36;
    alternate-background-color: #21222c;
    gridline-color: #44475a;
    border: 1px solid #44475a;
}
QHeaderView::section {
    background-color: #44475a;
    color: #f8f8f2;
    padding: 6px;
    border: none;
    font-weight: bold;
}
"""


class DropZone(QFrame):
    """File drag-and-drop zone with browse button."""

    def __init__(self, on_file_selected, parent: Optional[Any] = None):
        super().__init__(parent)
        self.on_file_selected = on_file_selected
        self.setAcceptDrops(True)
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Sunken)
        self.setStyleSheet("""
            QFrame {
                border: 2px dashed #6272a4;
                border-radius: 8px;
                background-color: #282a36;
                padding: 16px;
            }
            QFrame:hover {
                border-color: #bd93f9;
                background-color: #303342;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(t("drop_zone_title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #f8f8f2;")
        layout.addWidget(title)

        sub = QLabel(t("drop_zone_sub"))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("color: #6272a4; font-size: 12px;")
        layout.addWidget(sub)

        btn = QPushButton(t("btn_browse"))
        btn.clicked.connect(self._browse_file)
        btn.setStyleSheet("margin-top: 10px; background-color: #bd93f9; color: #282a36;")
        layout.addWidget(btn)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.on_file_selected(path)

    def _browse_file(self):
        filters = (
            "جميع الصيغ المدعومة (*.deb *.tar.gz *.tgz *.tar.xz *.tar.bz2 *.zip *.AppImage *.sh *.run *.bin);;"
            "حزم دبيان (*.deb);;"
            "أرشيفات مضغوطة (*.tar.gz *.tgz *.tar.xz *.tar.bz2 *.zip);;"
            "تطبيقات AppImage (*.AppImage);;"
            "سكربتات التثبيت (*.sh *.run *.bin);;"
            "جميع الملفات (*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(self, t("btn_browse"), str(Path.home()), filters)
        if file_path:
            self.on_file_selected(file_path)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(t("app_title"))
        self.resize(850, 750)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(DARK_STYLESHEET)

        self.current_file: Optional[str] = None
        self.current_plan: Optional[Plan] = None
        self.worker: Optional[InstallWorker] = None

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Top Header Bar
        header = QHBoxLayout()
        title_lbl = QLabel(t("app_title"))
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #50fa7b;")
        header.addWidget(title_lbl)
        header.addStretch()

        btn_doctor = QPushButton(t("btn_doctor"))
        btn_doctor.clicked.connect(self._show_doctor)
        btn_doctor.setStyleSheet("background-color: #44475a;")
        header.addWidget(btn_doctor)

        main_layout.addLayout(header)

        # Tab Widget
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Tab 1: Installer Tab
        tab_install = QWidget()
        self.install_layout = QVBoxLayout(tab_install)
        self.tabs.addTab(tab_install, t("tab_install"))

        # Scroll Area for Install Tab
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        self.card_layout = QVBoxLayout(scroll_content)
        scroll.setWidget(scroll_content)
        self.install_layout.addWidget(scroll)

        # 1. Drop Zone
        self.drop_zone = DropZone(self.on_file_selected)
        self.card_layout.addWidget(self.drop_zone)

        # 2. Package Info Card
        self.info_group = QGroupBox("معلومات الحزمة وإعدادات التثبيت")
        self.info_group.setVisible(False)
        self.card_layout.addWidget(self.info_group)
        self._setup_info_group()

        # 3. Progress and Log
        self.progress_group = QGroupBox("التقدم وسجل العمليات")
        self.progress_group.setVisible(False)
        self.card_layout.addWidget(self.progress_group)
        self._setup_progress_group()

        # 4. Result Screen
        self.result_group = QGroupBox("نتيجة التثبيت")
        self.result_group.setVisible(False)
        self.card_layout.addWidget(self.result_group)
        self._setup_result_group()

        # Tab 2: Installed Apps Tab
        self.installed_view = InstalledView()
        self.tabs.addTab(self.installed_view, t("tab_installed"))

    def _setup_info_group(self):
        layout = QVBoxLayout(self.info_group)

        # Metadata Row
        meta_row = QHBoxLayout()
        self.lbl_filename = QLabel()
        self.lbl_filesize = QLabel()
        self.lbl_format = QLabel()
        self.lbl_arch = QLabel()
        meta_row.addWidget(self.lbl_filename)
        meta_row.addWidget(self.lbl_filesize)
        meta_row.addWidget(self.lbl_format)
        meta_row.addWidget(self.lbl_arch)
        layout.addLayout(meta_row)

        # Editables: Display Name & Slug
        edit_layout = QHBoxLayout()

        edit_layout.addWidget(QLabel(t("lbl_display_name")))
        self.edit_name = QLineEdit()
        self.edit_name.textChanged.connect(self._on_name_changed)
        edit_layout.addWidget(self.edit_name)

        edit_layout.addWidget(QLabel(t("lbl_slug")))
        self.edit_slug = QLineEdit()
        self.edit_slug.textChanged.connect(self._on_slug_changed)
        edit_layout.addWidget(self.edit_slug)

        layout.addLayout(edit_layout)

        # Mode Selection
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel(t("lbl_mode")))
        self.rb_system = QRadioButton(t("mode_system"))
        self.rb_user = QRadioButton(t("mode_user"))
        self.rb_system.toggled.connect(self._rebuild_plan)
        mode_layout.addWidget(self.rb_system)
        mode_layout.addWidget(self.rb_user)
        layout.addLayout(mode_layout)

        # Warnings Box
        self.warnings_box = QLabel()
        self.warnings_box.setWordWrap(True)
        self.warnings_box.setStyleSheet("""
            background-color: #ffb86c;
            color: #282a36;
            font-weight: bold;
            padding: 8px;
            border-radius: 4px;
        """)
        self.warnings_box.setVisible(False)
        layout.addWidget(self.warnings_box)

        # Plan Steps View
        layout.addWidget(QLabel(t("plan_header")))
        self.steps_list = QTextEdit()
        self.steps_list.setReadOnly(True)
        self.steps_list.setMaximumHeight(130)
        layout.addWidget(self.steps_list)

        # Action Buttons
        btn_bar = QHBoxLayout()
        self.btn_install = QPushButton(t("btn_install"))
        self.btn_install.setStyleSheet("background-color: #50fa7b; color: #282a36; font-size: 14px; padding: 10px;")
        self.btn_install.clicked.connect(self._start_install)
        btn_bar.addWidget(self.btn_install)

        self.btn_cancel = QPushButton(t("btn_cancel"))
        self.btn_cancel.setStyleSheet("background-color: #ff5555; color: white;")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.clicked.connect(self._cancel_install)
        btn_bar.addWidget(self.btn_cancel)

        layout.addLayout(btn_bar)

    def _setup_progress_group(self):
        layout = QVBoxLayout(self.progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.log_edit.setMinimumHeight(150)
        layout.addWidget(self.log_edit)

        log_bar = QHBoxLayout()
        log_bar.addStretch()
        self.btn_open_log = QPushButton(t("btn_open_log"))
        self.btn_open_log.clicked.connect(self._open_log_file)
        log_bar.addWidget(self.btn_open_log)
        layout.addLayout(log_bar)

    def _setup_result_group(self):
        layout = QVBoxLayout(self.result_group)

        self.lbl_result_status = QLabel()
        self.lbl_result_status.setStyleSheet("font-size: 16px; font-weight: bold; color: #50fa7b;")
        layout.addWidget(self.lbl_result_status)

        cmd_row = QHBoxLayout()
        cmd_row.addWidget(QLabel(t("terminal_command")))
        self.edit_cmd = QLineEdit()
        self.edit_cmd.setReadOnly(True)
        cmd_row.addWidget(self.edit_cmd)

        self.btn_copy_cmd = QPushButton(t("btn_copy_cmd"))
        self.btn_copy_cmd.clicked.connect(self._copy_command)
        cmd_row.addWidget(self.btn_copy_cmd)

        layout.addLayout(cmd_row)

        action_row = QHBoxLayout()
        self.btn_launch = QPushButton(t("btn_launch_now"))
        self.btn_launch.setStyleSheet("background-color: #bd93f9; color: #282a36;")
        self.btn_launch.clicked.connect(self._launch_app)
        action_row.addWidget(self.btn_launch)

        self.btn_uninstall_res = QPushButton(t("btn_uninstall"))
        self.btn_uninstall_res.setStyleSheet("background-color: #ff5555; color: white;")
        self.btn_uninstall_res.clicked.connect(self._uninstall_from_result)
        action_row.addWidget(self.btn_uninstall_res)

        layout.addLayout(action_row)

        # Missing libs post install
        self.lbl_post_warnings = QLabel()
        self.lbl_post_warnings.setStyleSheet("color: #ffb86c; font-weight: bold;")
        self.lbl_post_warnings.setWordWrap(True)
        self.lbl_post_warnings.setVisible(False)
        layout.addWidget(self.lbl_post_warnings)

    def on_file_selected(self, file_path: str):
        """Handle selected file from Browse or Drag-and-drop."""
        self.current_file = file_path
        p = Path(file_path)
        if not p.exists():
            QMessageBox.warning(self, "خطأ", "الملف المحدد غير موجود.")
            return

        fmt = detect_format(file_path)
        if not fmt:
            QMessageBox.warning(self, "خطأ", "صيغة الملف غير مدعومة.")
            return

        size_mb = p.stat().st_size / (1024 * 1024)
        self.lbl_filename.setText(f"الملف: {p.name}")
        self.lbl_filesize.setText(f"الحجم: {size_mb:.1f} MB")
        self.lbl_format.setText(f"الصيغة: {fmt.upper()}")

        # Auto-derive slug
        slug = derive_slug(p.name)
        self.edit_slug.setText(slug)
        self.edit_name.setText(slug.replace("-", " ").title())

        # Mode default: AppImage defaults to user, others to system
        if fmt == "appimage":
            self.rb_user.setChecked(True)
        else:
            self.rb_system.setChecked(True)

        self.info_group.setVisible(True)
        self.progress_group.setVisible(False)
        self.result_group.setVisible(False)

        self._rebuild_plan()

    def _on_name_changed(self, text: str):
        """Handle display name edits."""
        pass

    def _on_slug_changed(self, text: str):
        """Real-time validation for ASCII [a-z0-9-]."""
        clean = text.strip()
        is_valid = bool(re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", clean))
        if not is_valid and clean:
            self.edit_slug.setStyleSheet("border: 2px solid #ff5555;")
            self.btn_install.setEnabled(False)
        else:
            self.edit_slug.setStyleSheet("")
            self.btn_install.setEnabled(True)
            self._rebuild_plan()

    def _rebuild_plan(self):
        """Re-generate plan based on current inputs."""
        if not self.current_file:
            return

        slug = self.edit_slug.text().strip()
        name = self.edit_name.text().strip()
        mode = "system" if self.rb_system.isChecked() else "user"

        try:
            self.current_plan = build_plan(
                self.current_file,
                options={"slug": slug, "display_name": name, "mode": mode},
            )

            # Display steps
            step_texts = []
            for i, s in enumerate(self.current_plan.steps):
                root_tag = " (Root)" if s.needs_root else ""
                step_texts.append(f"{i + 1}. {s.title_ar}{root_tag}")
            self.steps_list.setPlainText("\n".join(step_texts))

            # Display warnings
            if self.current_plan.warnings:
                self.warnings_box.setText("\n".join(self.current_plan.warnings))
                self.warnings_box.setVisible(True)
            else:
                self.warnings_box.setVisible(False)

        except Exception as e:
            self.steps_list.setPlainText(f"خطأ أثناء بناء الخطة: {e}")

    def _start_install(self):
        """Start the worker thread to execute the plan."""
        if not self.current_plan:
            return

        self.btn_install.setVisible(False)
        self.btn_cancel.setVisible(True)
        self.progress_group.setVisible(True)
        self.result_group.setVisible(False)
        self.log_edit.clear()

        self.worker = InstallWorker(self.current_plan, parent=self)
        self.worker.progress_signal.connect(self._on_worker_progress)
        self.worker.log_signal.connect(self._on_worker_log)
        self.worker.finished_signal.connect(self._on_worker_finished)
        self.worker.start()

    def _cancel_install(self):
        """Cancel running installation."""
        if self.worker:
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)

    def _on_worker_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.progress_bar.setFormat(f"{pct}% - {msg}")

    def _on_worker_log(self, line: str):
        self.log_edit.append(line)

    def _on_worker_finished(self, success: bool, msg: str, result_data: dict):
        self.btn_install.setVisible(True)
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setEnabled(True)
        self._last_result_data = result_data

        if success:
            self.result_group.setVisible(True)
            self.lbl_result_status.setText(msg)
            cmd = result_data.get("bin_cmd", "")
            self.edit_cmd.setText(cmd)

            # Merge result metadata into plan metadata for launch button
            if self.current_plan and self.current_plan.metadata is not None:
                for key in ("target_dir", "target_appimage_path", "exe_in_target", "desktop_file"):
                    val = result_data.get(key)
                    if val:
                        self.current_plan.metadata[key] = val

            # Check post-install warnings
            missing = result_data.get("missing_libs", [])
            if missing:
                txt = "مكتبات ناقصة قد يحتاجها البرنامج:\n" + "\n".join(
                    f"• {lib} -> يُنصح بتثبيت: {pkg}" for lib, pkg in missing
                )
                self.lbl_post_warnings.setText(txt)
                self.lbl_post_warnings.setVisible(True)
            else:
                self.lbl_post_warnings.setVisible(False)

            # Refresh installed tab
            self.installed_view.refresh_list()
        else:
            QMessageBox.critical(self, "فشل التثبيت", msg)

    def _copy_command(self):
        """Copy terminal command to clipboard."""
        cmd = self.edit_cmd.text().strip()
        if cmd:
            QGuiApplication.clipboard().setText(cmd)
            QMessageBox.information(self, "تم النسخ", "تم نسخ الأمر إلى الحافظة.")

    def _launch_app(self):
        """Launch newly installed app via multiple fallback strategies."""
        if not self.current_plan:
            return

        slug = self.current_plan.slug
        meta = self.current_plan.metadata or {}

        # If application is a CLI tool, launch it in a visible terminal
        is_terminal = meta.get("is_terminal", False)
        bin_cmd = self.edit_cmd.text().strip()
        if is_terminal:
            term = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal") or shutil.which("xterm")
            target_to_run = bin_cmd or slug
            if term:
                try:
                    subprocess.Popen(
                        [term, "-e", "bash", "-c", f'"{target_to_run}"; echo; read -rp "اضغط Enter للإغلاق..."'],
                        start_new_session=True,
                    )
                    return
                except Exception:
                    pass

        # Strategy 1: gtk-launch with the actual desktop file basename
        desktop_file_path = meta.get("desktop_file", "")
        if desktop_file_path:
            desktop_basename = os.path.basename(desktop_file_path)
        else:
            desktop_basename = f"{slug}.desktop"

        gtk_launch = shutil.which("gtk-launch")
        if gtk_launch:
            try:
                proc = subprocess.Popen(
                    [gtk_launch, desktop_basename],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                # Give it a moment to see if it fails immediately
                try:
                    proc.wait(timeout=2)
                    if proc.returncode == 0:
                        return  # Success
                except subprocess.TimeoutExpired:
                    return  # Still running = probably launched OK
            except Exception:
                pass  # Fall through to next strategy

        # Strategy 2: Run the binary symlink directly
        bin_cmd = self.edit_cmd.text().strip()
        if bin_cmd and os.path.exists(bin_cmd):
            try:
                subprocess.Popen(
                    [bin_cmd],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return
            except Exception:
                pass

        # Strategy 3: Run the executable directly from target dir
        target_dir = meta.get("target_dir", "")
        target_appimage = meta.get("target_appimage_path", "")
        exe_in_target = meta.get("exe_in_target", "")

        exe_path = ""
        if exe_in_target and os.path.exists(exe_in_target):
            exe_path = exe_in_target
        elif target_appimage and os.path.exists(target_appimage):
            exe_path = target_appimage
        elif target_dir and os.path.isdir(target_dir):
            # Look for executable in target dir
            if self.worker and self.worker.detected_executable:
                # Remap from staging to target dir
                exe_name = self.worker.detected_executable.name
                candidate = os.path.join(target_dir, exe_name)
                if os.path.exists(candidate):
                    exe_path = candidate

        if exe_path:
            try:
                subprocess.Popen(
                    [exe_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "تعذر التشغيل",
                    f"فشل تشغيل البرنامج مباشرة:\n{e}\n\nجرّب تشغيله من الطرفية:\n{bin_cmd or slug}",
                )
                return

        QMessageBox.information(
            self,
            "تنبيه",
            f"تعذر العثور على الملف التنفيذي لتشغيله مباشرة.\n\nجرّب تشغيله من الطرفية:\n{bin_cmd or slug}",
        )

    def _uninstall_from_result(self):
        """Uninstall app from result screen."""
        self.tabs.setCurrentIndex(1)
        self.installed_view.refresh_list()

    def _open_log_file(self):
        """Open current installation log file."""
        if self.worker and self.worker.log_file_path and self.worker.log_file_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.worker.log_file_path)))
        else:
            log_dir = Path.home() / ".local/share/smart-installer/logs"
            if log_dir.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir)))

    def _show_doctor(self):
        """Show system diagnostics dialog."""
        dlg = DoctorDialog(self)
        dlg.exec()

