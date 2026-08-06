#!/usr/bin/env bash
# 安裝 modbus-gripper udev rule → /dev/modbus-gripper
# Install the modbus-gripper udev rule → /dev/modbus-gripper
#
# 用法 | Usage: sudo ./scripts/install_udev.sh
set -euo pipefail

RULE_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../udev" && pwd)/99-modbus_gripper_usb.rules"
RULE_DST="/etc/udev/rules.d/99-modbus_gripper_usb.rules"
SYMLINK="/dev/modbus-gripper"

if [[ $EUID -ne 0 ]]; then
    echo "請用 sudo 執行 | Please run with sudo: sudo $0" >&2
    exit 1
fi

install -m 0644 "$RULE_SRC" "$RULE_DST"
udevadm control --reload-rules
udevadm trigger

# 等 udev 處理 | wait for udev to settle
udevadm settle --timeout=5 || true

if [[ -e "$SYMLINK" ]]; then
    echo "✅ 完成 | Done: $(ls -l "$SYMLINK" | awk '{print $NF, $(NF-1), $(NF-2)}')"
    echo "   $(ls -l "$SYMLINK")"
else
    echo "⚠️ Rule 已安裝，但 $SYMLINK 未出現。" >&2
    echo "   Rule installed, but $SYMLINK not found." >&2
    echo "   請檢查轉接器有冇插好，或重插 USB。" >&2
    echo "   Check the adapter is plugged in, or replug USB." >&2
    exit 1
fi
