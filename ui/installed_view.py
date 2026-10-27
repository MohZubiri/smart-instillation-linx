"""
Installed applications view module.
Displays installed packages recorded in manifests and handles uninstallation.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, List, Optional

try:
    from PyQt6.QtCore import Qt, QUrl
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtWidgets import (
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    pass

from core.manifest import InstallManifest, list_installed_manifests, uninstall_user_package
from core.privileges import run_privileged_operations
from i18n import t


class InstalledView(QWidget):
    """View displaying installed applications with Uninstall and Open Folder features."""

    def __init__(self, parent: Optional[Any] = None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.manifests: List[InstallManifest] = []

        layout = QVBoxLayout(self)

        # Header toolbar
        bar = QHBoxLayout()
        bar.addWidget(QLabel("البرامج التي تم تثبيتها بواسطة المثبت الذكي:"))
        bar.addStretch()

        self.btn_refresh = QPushButton("تحديث القائمة")
        self.btn_refresh.clicked.connect(self.refresh_list)
        bar.addWidget(self.btn_refresh)

        layout.addLayout(bar)

        # Manifests table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "اسم البرنامج",
            "المعرّف (Slug)",
            "وضع التثبيت",
            "الصيغة",
            "تاريخ التثبيت",
            "الإجراءات",
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

        self.refresh_list()

    def refresh_list(self):
        """Reload installed manifests and populate table."""
        self.manifests = list_installed_manifests()
        self.table.setRowCount(len(self.manifests))

        for row, m in enumerate(self.manifests):
            self.table.setItem(row, 0, QTableWidgetItem(m.display_name))
            self.table.setItem(row, 1, QTableWidgetItem(m.slug))
            self.table.setItem(row, 2, QTableWidgetItem("نظام" if m.mode == "system" else "مستخدم"))
            self.table.setItem(row, 3, QTableWidgetItem(m.format))
            self.table.setItem(row, 4, QTableWidgetItem(m.installed_at[:19].replace("T", " ")))

            # Actions cell with buttons
            cell_widget = QWidget()
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.setContentsMargins(2, 2, 2, 2)

            btn_open = QPushButton("فتح المجلد")
            btn_open.clicked.connect(lambda _, item=m: self._open_folder(item))
            cell_layout.addWidget(btn_open)

            btn_uninstall = QPushButton("إلغاء التثبيت")
            btn_uninstall.setStyleSheet("background-color: #ff5555; color: white;")
            btn_uninstall.clicked.connect(lambda _, item=m: self._uninstall_item(item))
            cell_layout.addWidget(btn_uninstall)

            self.table.setCellWidget(row, 5, cell_widget)

    def _open_folder(self, manifest: InstallManifest):
        """Open installation directory in file manager."""
        target_dir = None
        for p in manifest.created_paths:
            if Path(p).is_dir():
                target_dir = p
                break
        if target_dir and os.path.exists(target_dir):
            QDesktopServices.openUrl(QUrl.fromLocalFile(target_dir))
        else:
            QMessageBox.information(self, "تنبيه", "مجلد التثبيت غير موجود أو تم حذفه.")

    def _uninstall_item(self, manifest: InstallManifest):
        """Handle uninstallation of selected package."""
        confirm = QMessageBox.question(
            self,
            "تأكيد إلغاء التثبيت",
            t("uninstall_confirm", name=manifest.display_name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        if manifest.mode == "user":
            ok, msg = uninstall_user_package(manifest)
            if ok:
                QMessageBox.information(self, "نجاح", t("uninstall_success"))
                self.refresh_list()
            else:
                QMessageBox.warning(self, "فشل", t("uninstall_failed", error=msg))
        else:
            # System mode uninstall via helper
            ops = []
            # Remove deb package if deb
            if manifest.deb_package:
                ops.append({
                    "op": "apt_remove",
                    "args": {"package": manifest.deb_package},
                    "title_ar": f"إزالة الحزمة {manifest.deb_package} عبر APT",
                })

            # Remove recorded created paths
            for p in manifest.created_paths:
                ops.append({
                    "op": "remove",
                    "args": {"path": p},
                    "title_ar": f"حذف {p}",
                })

            ops.append({
                "op": "update_desktop_database",
                "args": {"dir": "/usr/share/applications"},
                "title_ar": "تحديث قاعدة بيانات الاختصارات",
            })

            ok, msg = run_privileged_operations(ops)
            if ok:
                # Remove system manifest file if still present
                m_path = Path("/var/lib/smart-installer") / f"{manifest.slug}.json"
                if m_path.exists():
                    try:
                        m_path.unlink()
                    except Exception:
                        pass
                QMessageBox.information(self, "نجاح", t("uninstall_success"))
                self.refresh_list()
            else:
                QMessageBox.warning(self, "فشل", t("uninstall_failed", error=msg))

