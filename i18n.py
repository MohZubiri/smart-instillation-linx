"""
Internationalization (i18n) module for Ubuntu Smart Package Installer.
Provides translations with Arabic as default and English support.
"""

from typing import Dict, Any

_CURRENT_LANG = "ar"

MESSAGES: Dict[str, Dict[str, str]] = {
    "app_title": {
        "ar": "المثبّت الذكي الشامل لنظام أوبونتو",
        "en": "Ubuntu Smart Package Installer"
    },
    "tab_install": {
        "ar": "تثبيت حزمة",
        "en": "Install Package"
    },
    "tab_installed": {
        "ar": "البرامج المثبّتة",
        "en": "Installed Applications"
    },
    "drop_zone_title": {
        "ar": "اسحب وأفلت ملف البرنامج هنا",
        "en": "Drag & drop package file here"
    },
    "drop_zone_sub": {
        "ar": "أو اضغط لاختيار ملف من جهازك (.deb, .tar.gz, .zip, .AppImage, .sh, ...)",
        "en": "or click to browse (.deb, .tar.gz, .zip, .AppImage, .sh, ...)"
    },
    "btn_browse": {
        "ar": "اختيار ملف البرنامج...",
        "en": "Browse package file..."
    },
    "btn_install": {
        "ar": "تثبيت البرنامج الآن",
        "en": "Install Program Now"
    },
    "btn_cancel": {
        "ar": "إلغاء التثبيت",
        "en": "Cancel Installation"
    },
    "btn_open_log": {
        "ar": "فتح ملف السجل",
        "en": "Open Log File"
    },
    "btn_copy_cmd": {
        "ar": "نسخ الأمر",
        "en": "Copy Command"
    },
    "btn_launch_now": {
        "ar": "تشغيل الآن",
        "en": "Launch Now"
    },
    "btn_uninstall": {
        "ar": "إلغاء التثبيت",
        "en": "Uninstall"
    },
    "btn_open_folder": {
        "ar": "فتح المجلد",
        "en": "Open Folder"
    },
    "btn_doctor": {
        "ar": "فحص النظام (Doctor)",
        "en": "System Doctor"
    },
    "lbl_file_name": {
        "ar": "اسم الملف:",
        "en": "File Name:"
    },
    "lbl_file_size": {
        "ar": "الحجم:",
        "en": "File Size:"
    },
    "lbl_file_format": {
        "ar": "الصيغة المكتشفة:",
        "en": "Detected Format:"
    },
    "lbl_architecture": {
        "ar": "المعمارية:",
        "en": "Architecture:"
    },
    "lbl_display_name": {
        "ar": "الاسم المعروض:",
        "en": "Display Name:"
    },
    "lbl_slug": {
        "ar": "المعرّف البرمجي (Slug):",
        "en": "Program Identifier (Slug):"
    },
    "lbl_mode": {
        "ar": "وضع التثبيت:",
        "en": "Install Mode:"
    },
    "mode_system": {
        "ar": "نظام (/opt - لجميع المستخدمين، يتطلب root)",
        "en": "System (/opt - all users, requires root)"
    },
    "mode_user": {
        "ar": "مستخدم (~/.local/opt - للمستخدم الحالي فقط)",
        "en": "User (~/.local/opt - current user only)"
    },
    "plan_header": {
        "ar": "خطة التثبيت المعتمدة:",
        "en": "Installation Execution Plan:"
    },
    "log_output": {
        "ar": "سجل العمليات:",
        "en": "Operations Log:"
    },
    "install_success": {
        "ar": "تم تثبيت البرنامج بنجاح!",
        "en": "Installation completed successfully!"
    },
    "install_failed": {
        "ar": "فشل التثبيت! تم التراجع عن التغييرات للحفاظ على استقرار النظام.",
        "en": "Installation failed! Rollback executed to maintain system stability."
    },
    "install_cancelled": {
        "ar": "تم إلغاء التثبيت من قبل المستخدم والتراجع عن التغييرات.",
        "en": "Installation cancelled by user and changes rolled back."
    },
    "terminal_command": {
        "ar": "أمر الطرفية:",
        "en": "Terminal Command:"
    },
    "post_install_warnings": {
        "ar": "تنبيهات ما بعد التثبيت (مكتبات قد تنقص لتشغيل البرنامج):",
        "en": "Post-install warnings (missing runtime libraries):"
    },
    "warning_arch_mismatch": {
        "ar": "تحذير: معمارية الحزمة ({pkg_arch}) لا تتطابق مع معمارية النظام ({sys_arch}).",
        "en": "Warning: Package architecture ({pkg_arch}) does not match system ({sys_arch})."
    },
    "warning_fuse2_missing": {
        "ar": "تنبيه: حزمة libfuse.so.2 غير مثبتة في النظام. قد تحتاج تثبيت libfuse2t64 أو استخدام وضع الاستخراج المباشر لـ AppImage.",
        "en": "Notice: libfuse.so.2 is missing. You may need libfuse2t64 or extract-and-run mode."
    },
    "warning_exfat": {
        "ar": "تنبيه: ملف التثبيت موجود على قرص بنظام ملفات {fs_type} (لا يدعم صلاحيات لينكس أو الروابط الرمزية). سيتم نسخ الملف أولاً قبل معالجته.",
        "en": "Notice: Source file is on {fs_type} filesystem. It will be copied before processing."
    },
    "warning_space": {
        "ar": "تحذير: المساحة المتوفرة ({avail} MB) قد لا تكفي لحجم البرنامج التقديري ({needed} MB).",
        "en": "Warning: Available space ({avail} MB) might be insufficient for needed ({needed} MB)."
    },
    "warning_conflict": {
        "ar": "تنبيه: المعرف '{slug}' أو مجلد التثبيت موجود مسبقاً في النظام.",
        "en": "Notice: Identifier '{slug}' or target folder already exists in the system."
    },
    "running_as_root_error": {
        "ar": "خطأ أمني: لا يمكن تشغيل هذا البرنامج بصلاحيات root مباشرة! شغّله كمستخدم عادي وسيطلب النظام الصلاحيات عند الحاجة عبر pkexec.",
        "en": "Security Error: Do not run this application directly as root. Run as standard user."
    },
    "single_instance_error": {
        "ar": "توجد عملية تثبيت أخرى قيد التشغيل حالياً. يرجى الانتظار حتى تنتهي.",
        "en": "Another installation is already in progress. Please wait."
    },
    "uninstall_confirm": {
        "ar": "هل أنت متأكد من رغبتك في إلغاء تثبيت '{name}' وحذف كافة ملفاته؟",
        "en": "Are you sure you want to uninstall '{name}' and remove all its files?"
    },
    "uninstall_success": {
        "ar": "تم إلغاء التثبيت بنجاح.",
        "en": "Uninstallation completed successfully."
    },
    "uninstall_failed": {
        "ar": "فشل إلغاء التثبيت: {error}",
        "en": "Uninstallation failed: {error}"
    },
    "step_extract": {
        "ar": "فك ضغط الأرشيف في مجلد التحضير",
        "en": "Extracting archive in staging area"
    },
    "step_inspect": {
        "ar": "فحص محتويات الحزمة واكتشاف الملف التنفيذي والأيقونة",
        "en": "Inspecting package content and detecting executable & icon"
    },
    "step_move": {
        "ar": "نقل ملفات البرنامج إلى مسار التثبيت النهائي",
        "en": "Moving application files to installation target"
    },
    "step_permissions": {
        "ar": "ضبط صلاحيات المجلد والملف التنفيذي",
        "en": "Configuring folder and executable permissions"
    },
    "step_chrome_sandbox": {
        "ar": "إصلاح صلاحيات أمان chrome-sandbox (chmod 4755)",
        "en": "Fixing chrome-sandbox security permissions (chmod 4755)"
    },
    "step_symlink": {
        "ar": "إنشاء رابط رمزي في مجلد الأوامر للتشغيل من الطرفية",
        "en": "Creating symlink in bin directory for terminal access"
    },
    "step_desktop_file": {
        "ar": "إنشاء اختصار في قائمة التطبيقات (.desktop)",
        "en": "Creating application menu shortcut (.desktop)"
    },
    "step_icon": {
        "ar": "تثبيت أيقونة التطبيق في دليل الأيقونات القياسي",
        "en": "Installing application icon in standard icon theme"
    },
    "step_manifest": {
        "ar": "تسجيل معلومات التثبيت في سجل النظام لإتاحة إلغاء التثبيت",
        "en": "Registering install manifest for uninstallation support"
    },
    "step_apt_install": {
        "ar": "تثبيت حزمة .deb عبر أداة إدارة حزم النظام (APT)",
        "en": "Installing .deb package via APT"
    },
    "step_run_script": {
        "ar": "تشغيل سكربت التثبيت",
        "en": "Executing installer script"
    },
    "step_cleanup": {
        "ar": "تنظيف الملفات المؤقتة ومجلد التحضير",
        "en": "Cleaning up temporary files and staging area"
    }
}


def t(key: str, **kwargs: Any) -> str:
    """Retrieve translated string with optional formatting."""
    lang_dict = MESSAGES.get(key, {})
    template = lang_dict.get(_CURRENT_LANG, lang_dict.get("ar", key))
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template


def set_language(lang: str) -> None:
    """Set the application language ('ar' or 'en')."""
    global _CURRENT_LANG
    if lang in ("ar", "en"):
        _CURRENT_LANG = lang

