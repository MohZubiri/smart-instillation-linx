#!/usr/bin/env python3
"""
Entry point for Ubuntu Smart Package Installer.
Handles --dry-run CLI mode, root check, and Qt application initialization.
"""

import argparse
import os
import sys
from pathlib import Path

from core.plan import build_plan
from i18n import t


def main():
    parser = argparse.ArgumentParser(
        description="Ubuntu Smart Package Installer / المثبت الذكي الشامل لنظام أوبونتو"
    )
    parser.add_argument("file", nargs="?", help="Package file to install")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the installation plan as JSON to stdout without executing",
    )
    parser.add_argument(
        "--mode",
        choices=["system", "user"],
        help="Installation mode: system (/opt) or user (~/.local/opt)",
    )
    parser.add_argument("--slug", help="Custom identifier (slug) for the package")
    parser.add_argument("--name", help="Display name for the application")

    args = parser.parse_args()

    # Dry-run CLI mode
    if args.dry_run:
        if not args.file:
            print("Error: --dry-run requires a file argument.", file=sys.stderr)
            sys.exit(1)

        options = {}
        if args.mode:
            options["mode"] = args.mode
        if args.slug:
            options["slug"] = args.slug
        if args.name:
            options["display_name"] = args.name

        try:
            plan = build_plan(args.file, options)
            print(plan.to_json(indent=2))
            sys.exit(0)
        except Exception as e:
            print(f"Error building plan: {e}", file=sys.stderr)
            sys.exit(2)

    # Security check: Never run the GUI as root directly
    if os.geteuid() == 0:
        print(
            "خطأ أمني: يمنع تشغيل واجهة المثبت الذكي بصلاحيات root مباشرة!\n"
            "Security Error: Do not run the Smart Package Installer GUI directly as root.\n"
            "Run as a standard user; root privileges will be requested safely via pkexec when needed.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Launch GUI
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication
        from ui.main_window import MainWindow
    except ImportError as e:
        print(
            f"Error importing PyQt6: {e}\n"
            "Please ensure python3-pyqt6 is installed via: sudo apt install python3-pyqt6",
            file=sys.stderr,
        )
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setApplicationName("SmartPackageInstaller")

    window = MainWindow()
    if args.file and os.path.exists(args.file):
        window.on_file_selected(os.path.abspath(args.file))

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

