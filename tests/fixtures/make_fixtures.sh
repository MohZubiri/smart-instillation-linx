#!/usr/bin/env bash
# ==============================================================================
# make_fixtures.sh - Generate test fixtures for Smart Package Installer
# Assembles real test packages in /tmp and packages them for the test suite.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="/tmp/smart-installer-fixtures-build"
rm -rf "${WORK_DIR}"
mkdir -p "${WORK_DIR}"

# 1. Compile helper minimal ELF binary
echo "Compiling minimal ELF binary..."
echo 'int main(){return 0;}' | gcc -x c - -o "${WORK_DIR}/minimal_elf"

# Create minimal 1x1 PNG bytes
create_dummy_png() {
    local target="$1"
    mkdir -p "$(dirname "$target")"
    python3 -c "
import struct, zlib
signature = b'\x89PNG\r\n\x1a\n'
ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
ihdr_crc = struct.pack('>I', zlib.crc32(b'IHDR' + ihdr_data))
ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + ihdr_crc
raw_pixel = b'\x00\x50\xfa\x7b'
idat_data = zlib.compress(raw_pixel)
idat_crc = struct.pack('>I', zlib.crc32(b'IDAT' + idat_data))
idat = struct.pack('>I', len(idat_data)) + b'IDAT' + idat_data + idat_crc
iend_crc = struct.pack('>I', zlib.crc32(b'IEND'))
iend = struct.pack('>I', 0) + b'IEND' + iend_crc
with open('$target', 'wb') as f:
    f.write(signature + ihdr + idat + iend)
"
}

# ------------------------------------------------------------------------------
# Fixture 1: Electron Archive (dummy-electron-linux-x64.tar.gz)
# ------------------------------------------------------------------------------
echo "Building Fixture 1: Electron Archive..."
E_DIR="${WORK_DIR}/dummy-electron"
mkdir -p "${E_DIR}/resources/app"
cp "${WORK_DIR}/minimal_elf" "${E_DIR}/dummy-electron"
chmod +x "${E_DIR}/dummy-electron"
cp "${WORK_DIR}/minimal_elf" "${E_DIR}/chrome-sandbox"
chmod +x "${E_DIR}/chrome-sandbox"

cat <<'EOF' > "${E_DIR}/resources/app/package.json"
{
  "name": "dummy-electron-app",
  "productName": "Dummy Electron",
  "version": "1.0.0"
}
EOF

create_dummy_png "${E_DIR}/resources/icon.png"

tar -czf "${SCRIPT_DIR}/dummy-electron-linux-x64.tar.gz" -C "${WORK_DIR}" "dummy-electron"

# ------------------------------------------------------------------------------
# Fixture 2: JetBrains Archive (dummy-jetbrains.tar.gz)
# ------------------------------------------------------------------------------
echo "Building Fixture 2: JetBrains Archive..."
J_DIR="${WORK_DIR}/dummy-jetbrains"
mkdir -p "${J_DIR}/bin"
cat <<'EOF' > "${J_DIR}/bin/idea.sh"
#!/bin/sh
echo "Launching IDE..."
EOF
chmod +x "${J_DIR}/bin/idea.sh"

cat <<'EOF' > "${J_DIR}/bin/idea.svg"
<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#000"/></svg>
EOF

tar -czf "${SCRIPT_DIR}/dummy-jetbrains.tar.gz" -C "${WORK_DIR}" "dummy-jetbrains"

# ------------------------------------------------------------------------------
# Fixture 3: Single Binary Archive (dummy-single-binary.tar.gz)
# ------------------------------------------------------------------------------
echo "Building Fixture 3: Single Binary Archive..."
S_DIR="${WORK_DIR}/single_bin_staging"
mkdir -p "${S_DIR}"
cp "${WORK_DIR}/minimal_elf" "${S_DIR}/mycli"
chmod +x "${S_DIR}/mycli"
tar -czf "${SCRIPT_DIR}/dummy-single-binary.tar.gz" -C "${S_DIR}" "mycli"

# ------------------------------------------------------------------------------
# Fixture 4: Debian Package (dummy-tool_1.0.0_all.deb)
# ------------------------------------------------------------------------------
echo "Building Fixture 4: Debian Package..."
DEB_DIR="${WORK_DIR}/dummy-tool_1.0.0_all"
mkdir -p "${DEB_DIR}/DEBIAN"
mkdir -p "${DEB_DIR}/usr/bin"
mkdir -p "${DEB_DIR}/usr/share/applications"
chmod 0755 "${DEB_DIR}" "${DEB_DIR}/DEBIAN"

cat <<'EOF' > "${DEB_DIR}/DEBIAN/control"
Package: dummy-tool
Version: 1.0.0
Architecture: all
Maintainer: Test <test@example.com>
Description: Dummy tool for Smart Installer testing
EOF

cat <<'EOF' > "${DEB_DIR}/usr/bin/dummy-tool"
#!/bin/sh
echo "Dummy Tool 1.0"
EOF
chmod 0755 "${DEB_DIR}/usr/bin/dummy-tool"

cat <<'EOF' > "${DEB_DIR}/usr/share/applications/dummy-tool.desktop"
[Desktop Entry]
Type=Application
Version=1.5
Name=Dummy Tool
Exec=/usr/bin/dummy-tool %U
Icon=application-x-executable
Terminal=false
Categories=Utility;
EOF
chmod 0644 "${DEB_DIR}/usr/share/applications/dummy-tool.desktop"

dpkg-deb -b "${DEB_DIR}" "${SCRIPT_DIR}/dummy-tool_1.0.0_all.deb"

# ------------------------------------------------------------------------------
# Fixture 5: Shell Installer Script (dummy-installer.sh)
# ------------------------------------------------------------------------------
echo "Building Fixture 5: Shell Script..."
cat <<'EOF' > "${SCRIPT_DIR}/dummy-installer.sh"
#!/bin/bash
echo "Installing dummy tool..."
echo "Done!"
exit 0
EOF
chmod +x "${SCRIPT_DIR}/dummy-installer.sh"

# ------------------------------------------------------------------------------
# Fixture 6: AppImage (Obsidian-1.6.7.AppImage)
# ------------------------------------------------------------------------------
echo "Building Fixture 6: AppImage..."
# Create a valid ELF file with 'AppImage' marker in header
AI_FILE="${SCRIPT_DIR}/Obsidian-1.6.7.AppImage"
cp "${WORK_DIR}/minimal_elf" "${AI_FILE}"
# Embed AppImage magic AI\x02
python3 -c "
with open('${AI_FILE}', 'r+b') as f:
    f.seek(8)
    f.write(b'AI\x02AppImage')
"
chmod +x "${AI_FILE}"

# Cleanup temporary workdir
rm -rf "${WORK_DIR}"
echo "All fixtures generated successfully in ${SCRIPT_DIR}."
