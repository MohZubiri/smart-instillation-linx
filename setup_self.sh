#!/usr/bin/env bash
# ==============================================================================
# setup_self.sh - Installation & Setup script for Smart Package Installer
# Sets up dependencies, installs files into /opt/smart-installer, configures
# Polkit policy, desktop integration, and system wrappers.
# Conforms strictly to Section 7 of project specifications.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/smart-installer"
WRAPPER_BIN="/usr/local/bin/smart-installer"
POLKIT_POLICY="/usr/share/polkit-1/actions/org.smartinstaller.helper.policy"
DESKTOP_FILE="/usr/share/applications/smart-installer.desktop"
ICON_DIR="/usr/share/icons/hicolor/scalable/apps"
ICON_FILE="${ICON_DIR}/smart-installer.svg"

# Re-exec as root if not currently root
if [[ "${EUID}" -ne 0 ]]; then
    echo "إعادة تشغيل بصلاحيات الجذر (Root)..."
    if command -v pkexec >/dev/null 2>&1; then
        exec pkexec bash "$0" "$@"
    elif command -v sudo >/dev/null 2>&1; then
        exec sudo bash "$0" "$@"
    else
        echo "خطأ: يتطلب تثبيت هذا البرنامج صلاحيات الجذر (Root)." >&2
        exit 1
    fi
fi

# Handle --uninstall
if [[ "${1:-}" == "--uninstall" ]]; then
    echo "بدء إزالة المثبّت الذكي من النظام..."

    echo "حذف ملفات التطبيق من ${INSTALL_DIR}..."
    rm -rf "${INSTALL_DIR}"

    echo "حذف أمر الطرفية ${WRAPPER_BIN}..."
    rm -f "${WRAPPER_BIN}"

    echo "حذف سياسة Polkit ${POLKIT_POLICY}..."
    rm -f "${POLKIT_POLICY}"

    echo "حذف اختصار سطح المكتب ${DESKTOP_FILE}..."
    rm -f "${DESKTOP_FILE}"

    echo "حذف أيقونة التطبيق ${ICON_FILE}..."
    rm -f "${ICON_FILE}"

    echo "تحديث قواعد بيانات النظام..."
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database /usr/share/applications || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f /usr/share/icons/hicolor || true

    echo "تمت إزالة المثبّت الذكي بنجاح من النظام."
    exit 0
fi

echo "======================================================"
echo " تثبيت المثبّت الذكي الشامل لنظام أوبونتو (Smart Package Installer)"
echo "======================================================"

# 1. Install prerequisites using apt (no global pip)
echo "[1/6] التحقق من المتطلبات وتثبيت الحزم الأساسية..."
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq || true
apt-get install -y \
    python3 \
    python3-pyqt6 \
    desktop-file-utils \
    policykit-1 \
    libfuse2t64 || apt-get install -y libfuse2 || true

# If python3-pyqt6 was not found in repo, prepare a venv
PYTHON_EXEC="/usr/bin/python3"
if ! python3 -c "import PyQt6" >/dev/null 2>&1; then
    echo "PyQt6 غير متوفر كحزمة نظام مباشرة. جاري إعداد بيئة افتراضية داخل ${INSTALL_DIR}/venv..."
    apt-get install -y python3-venv python3-pip || true
    mkdir -p "${INSTALL_DIR}"
    python3 -m venv "${INSTALL_DIR}/venv"
    "${INSTALL_DIR}/venv/bin/pip" install -r "${SCRIPT_DIR}/requirements.txt"
    PYTHON_EXEC="${INSTALL_DIR}/venv/bin/python3"
fi

# 2. Copy project files to /opt/smart-installer (excluding .git, __pycache__, tests)
echo "[2/6] نسخ ملفات المشروع إلى ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}"

# Clean existing installation while preserving venv if present
find "${INSTALL_DIR}" -mindepth 1 -maxdepth 1 ! -name 'venv' -exec rm -rf {} +

cp -r "${SCRIPT_DIR}/main.py" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/i18n.py" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/privileged_helper.py" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/ui" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/core" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/handlers" "${INSTALL_DIR}/"
cp -r "${SCRIPT_DIR}/resources" "${INSTALL_DIR}/"

# Clean any pycache copied
find "${INSTALL_DIR}" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# 3. Security hardening: chown root:root & chmod go-w
echo "[3/6] ضبط الأمان وصلاحيات الوصول (chown root:root & chmod go-w)..."
chown -R root:root "${INSTALL_DIR}"
chmod -R go-w "${INSTALL_DIR}"
chmod +x "${INSTALL_DIR}/privileged_helper.py"
chmod +x "${INSTALL_DIR}/main.py"

# Create state directory for system manifests
mkdir -p /var/lib/smart-installer
chmod 0755 /var/lib/smart-installer

# 4. Install Polkit policy
echo "[4/6] تثبيت سياسة Polkit المعتمدة..."
mkdir -p /usr/share/polkit-1/actions
cp "${SCRIPT_DIR}/resources/org.smartinstaller.helper.policy" "${POLKIT_POLICY}"
chmod 0644 "${POLKIT_POLICY}"

# 5. Create wrapper script in /usr/local/bin
echo "[5/6] إنشاء أمر الطرفية ${WRAPPER_BIN}..."
mkdir -p /usr/local/bin
cat <<EOF > "${WRAPPER_BIN}"
#!/bin/sh
exec ${PYTHON_EXEC} ${INSTALL_DIR}/main.py "\$@"
EOF
chmod 0755 "${WRAPPER_BIN}"

# 6. Install Icon and Desktop file
echo "[6/6] تثبيت الأيقونة واختصار قائمة التطبيقات..."
mkdir -p "${ICON_DIR}"
cp "${SCRIPT_DIR}/resources/smart-installer.svg" "${ICON_FILE}"
chmod 0644 "${ICON_FILE}"

mkdir -p /usr/share/applications
cp "${SCRIPT_DIR}/resources/smart-installer.desktop" "${DESKTOP_FILE}"
chmod 0644 "${DESKTOP_FILE}"

# Validate and update databases
if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "${DESKTOP_FILE}" || true
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi

echo "======================================================"
echo " اكتمل التثبيت بنجاح!"
echo " يمكنك الآن تشغيل البرنامج عبر الأمر: smart-installer"
echo " أو من خلال قائمة التطبيقات: 'المثبّت الذكي'"
echo "======================================================"

