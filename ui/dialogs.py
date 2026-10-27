"""
Dialogs module: Executable selection, icon selection, conflict resolution,
script approval, and system doctor check.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QButtonGroup,
        QCheckBox,
        QDialog,
        QDialogButtonBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMessageBox,
        QPushButton,
        QRadioButton,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QVBoxLayout,
    )
except ImportError:
    pass

from core.analyzers import check_fuse2_available
from core.privileges import run_privileged_operations
from i18n import t


class ExecutableSelectDialog(QDialog):
    """Dialog to choose the main executable when multiple candidates exist."""

    def __init__(self, candidates: List[Path], parent: Optional[Any] = None):
        super().__init__(parent)
        self.setWindowTitle("اختيار الملف التنفيذي الرئيسي")
        self.resize(550, 350)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.selected_path: Optional[Path] = None

        layout = QVBoxLayout(self)
        lbl = QLabel("تم العثور على عدة ملفات تنفيذية في الحزمة. يرجى اختيار الملف الرئيسي لتشغيل البرنامج:")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        self.list_widget = QListWidget()
        for c in candidates:
            item = QListWidgetItem(f"{c.name} ({c})")
            item.setData(Qt.ItemDataRole.UserRole, c)
            self.list_widget.addItem(item)
        if candidates:
            self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        curr = self.list_widget.currentItem()
        if curr:
            self.selected_path = curr.data(Qt.ItemDataRole.UserRole)
        self.accept()


class IconSelectDialog(QDialog):
    """Dialog to choose application icon among multiple candidates."""

    def __init__(self, candidates: List[Path], parent: Optional[Any] = None):
        super().__init__(parent)
        self.setWindowTitle("اختيار أيقونة البرنامج")
        self.resize(500, 300)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.selected_icon: Optional[Path] = None

        layout = QVBoxLayout(self)
        lbl = QLabel("تم العثور على أكثر من أيقونة. يرجى اختيار الأيقونة المفضلة:")
        layout.addWidget(lbl)

        self.list_widget = QListWidget()
        for icon in candidates:
            item = QListWidgetItem(f"{icon.name} ({icon})")
            item.setData(Qt.ItemDataRole.UserRole, icon)
            self.list_widget.addItem(item)
        if candidates:
            self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        curr = self.list_widget.currentItem()
        if curr:
            self.selected_icon = curr.data(Qt.ItemDataRole.UserRole)
        self.accept()


class ConflictDialog(QDialog):
    """Dialog to resolve naming or target path conflicts."""

    def __init__(self, conflict_data: Dict[str, Any], parent: Optional[Any] = None):
        super().__init__(parent)
        self.setWindowTitle("تعارض في مسار التثبيت أو الاسم")
        self.resize(520, 320)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.action = "cancel"  # "upgrade", "rename", "cancel"
        self.new_slug = conflict_data.get("suggested_bin_name", "")

        layout = QVBoxLayout(self)

        msg_lbl = QLabel("\n".join(conflict_data.get("messages", ["يوجد تعارض في التثبيت."])))
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("color: #ffb86c; font-weight: bold;")
        layout.addWidget(msg_lbl)

        lbl = QLabel("كيف ترغب في المتابعة؟")
        layout.addWidget(lbl)

        self.btn_group = QButtonGroup(self)
        self.rb_upgrade = QRadioButton("ترقية واستبدال التثبيت السابق (Upgrade)")
        self.rb_rename = QRadioButton("استخدام معرّف بديل (Rename):")
        self.rb_cancel = QRadioButton("إلغاء التثبيت")

        self.btn_group.addButton(self.rb_upgrade)
        self.btn_group.addButton(self.rb_rename)
        self.btn_group.addButton(self.rb_cancel)

        if conflict_data.get("has_manifest"):
            self.rb_upgrade.setChecked(True)
        else:
            self.rb_rename.setChecked(True)

        layout.addWidget(self.rb_upgrade)

        rename_layout = QHBoxLayout()
        rename_layout.addWidget(self.rb_rename)
        self.edit_rename = QLineEdit(self.new_slug)
        rename_layout.addWidget(self.edit_rename)
        layout.addLayout(rename_layout)

        layout.addWidget(self.rb_cancel)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        if self.rb_upgrade.isChecked():
            self.action = "upgrade"
        elif self.rb_rename.isChecked():
            self.action = "rename"
            self.new_slug = self.edit_rename.text().strip()
        else:
            self.action = "cancel"
        self.accept()


class ScriptApprovalDialog(QDialog):
    """Approval and configuration dialog for .sh, .run, .bin installer scripts."""

    def __init__(self, script_info: Dict[str, Any], parent: Optional[Any] = None):
        super().__init__(parent)
        self.setWindowTitle("موافقة وإعداد تشغيل سكربت التثبيت")
        self.resize(650, 500)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.run_as_root = False
        self.run_in_terminal = True
        self.extra_args = ""

        layout = QVBoxLayout(self)

        notice = QLabel("تنبيه أمني: سكربتات التثبيت تنفّذ كوداً برمجياً على جهازك. يُرجى مراجعة التفاصيل قبل الموافقة:")
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #f1fa8c; font-weight: bold;")
        layout.addWidget(notice)

        # Preview box
        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        preview.setStyleSheet("background-color: #282a36; color: #f8f8f2; font-family: monospace;")
        first_lines = script_info.get("preview", {}).get("first_lines", [])
        preview.setPlainText("\n".join(first_lines) if first_lines else "لا توجد أسطر نصية متاحة للمعاينة.")
        layout.addWidget(preview)

        # Execution privilege
        lbl_priv = QLabel("صلاحيات التشغيل:")
        layout.addWidget(lbl_priv)
        self.rb_user = QRadioButton("المستخدم الحالي (بدون صلاحيات جذر - آمن ومستحسن)")
        self.rb_root = QRadioButton("صلاحيات الجذر (Root - يتطلب إدخال كلمة المرور عبر pkexec)")
        if script_info.get("preview", {}).get("contains_sudo"):
            self.rb_root.setChecked(True)
            self.rb_root.setText("صلاحيات الجذر (Root) [موصى به لوجود أوامر sudo في السكربت]")
        else:
            self.rb_user.setChecked(True)
        layout.addWidget(self.rb_user)
        layout.addWidget(self.rb_root)

        # Execution target
        lbl_loc = QLabel("مكان التشغيل:")
        layout.addWidget(lbl_loc)
        self.rb_term = QRadioButton("في نافذة طرفية مستقلة (Terminal - للسكربتات التفاعلية والأسئلة)")
        self.rb_internal = QRadioButton("في السجل الداخلي للبرنامج")
        self.rb_term.setChecked(True)
        layout.addWidget(self.rb_term)
        layout.addWidget(self.rb_internal)

        # Extra args
        args_layout = QHBoxLayout()
        args_layout.addWidget(QLabel("وسائط إضافية (خيارات السكربت):"))
        self.edit_args = QLineEdit()
        self.edit_args.setPlaceholderText("مثال: -b -p /opt/app")
        args_layout.addWidget(self.edit_args)
        layout.addLayout(args_layout)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_accept(self):
        self.run_as_root = self.rb_root.isChecked()
        self.run_in_terminal = self.rb_term.isChecked()
        self.extra_args = self.edit_args.text().strip()
        self.accept()


class DoctorDialog(QDialog):
    """System requirements and diagnostics dialog (Doctor)."""

    def __init__(self, parent: Optional[Any] = None):
        super().__init__(parent)
        self.setWindowTitle("فحص متطلبات النظام (Doctor)")
        self.resize(600, 420)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("حالة الأدوات والمتطلبات الأساسية للمثبت الذكي:"))

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["الأداة / الحزمة", "الحالة", "المسار / الملاحظة"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.btn_fix = QPushButton("تثبيت المتطلبات الناقصة تلقائياً")
        self.btn_fix.setStyleSheet("background-color: #50fa7b; color: #282a36; font-weight: bold; padding: 6px;")
        self.btn_fix.clicked.connect(self._fix_missing)
        layout.addWidget(self.btn_fix)

        self.check_all()

    def check_all(self):
        """Perform system checks."""
        tools = [
            ("dpkg-deb", "أداة حزم دبيان", bool(shutil.which("dpkg-deb"))),
            ("apt-get", "مدير حزم النظام", bool(shutil.which("apt-get"))),
            ("tar", "أداة الأرشيف", bool(shutil.which("tar"))),
            ("update-desktop-database", "تحديث اختصارات سطح المكتب", bool(shutil.which("update-desktop-database"))),
            ("desktop-file-validate", "التحقق من ملفات .desktop", bool(shutil.which("desktop-file-validate"))),
            ("pkexec", "إدارة صلاحيات polkit", bool(shutil.which("pkexec"))),
            ("gtk-launch", "تشغيل التطبيقات", bool(shutil.which("gtk-launch"))),
            ("ldd", "فحص المكتبات المشتركة", bool(shutil.which("ldd"))),
            ("x-terminal-emulator", "الطرفية الافتراضية", bool(shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal"))),
            ("libfuse.so.2", "مكتبة FUSE لـ AppImage", check_fuse2_available()),
        ]

        self.table.setRowCount(len(tools))
        has_missing = False

        for row, (cmd, desc, ok) in enumerate(tools):
            self.table.setItem(row, 0, QTableWidgetItem(f"{cmd} ({desc})"))
            status_item = QTableWidgetItem("متوفرة ✓" if ok else "ناقصة ✗")
            status_item.setForeground(Qt.GlobalColor.green if ok else Qt.GlobalColor.red)
            self.table.setItem(row, 1, status_item)

            path_or_note = shutil.which(cmd) if ok and cmd != "libfuse.so.2" else ("متوفرة بالنظام" if ok else "مطلوب تثبيتها")
            self.table.setItem(row, 2, QTableWidgetItem(path_or_note or ""))

            if not ok:
                has_missing = True

        self.btn_fix.setEnabled(has_missing)

    def _fix_missing(self):
        """Install missing dependencies via privileged helper."""
        pkgs = ["desktop-file-utils", "policykit-1", "libfuse2t64"]
        ops = [
            {
                "op": "run_script",
                "args": {
                    "script_path": "/usr/bin/apt-get",
                    "args": ["install", "-y"] + pkgs,
                },
                "title_ar": "تثبيت حزم النظام الناقصة",
            }
        ]
        ok, msg = run_privileged_operations(ops)
        if ok:
            QMessageBox.information(self, "نجاح", "تم تثبيت المتطلبات بنجاح.")
            self.check_all()
        else:
            QMessageBox.warning(self, "فشل", f"تعذر تثبيت المتطلبات: {msg}")

