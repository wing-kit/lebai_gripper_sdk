# xArm 整合 | xArm Integration

經 xArm tool-end RS485 控制 Lebai 夾爪（唔使 USB 轉接器）。
夾爪 M8-8P 直插 xArm 手腕接口（24V 棕 / GND 綠 / 485A 橙 pin5 / 485B 藍 pin6，同 xArm pinout 一致）。

Drive the Lebai gripper through the xArm tool-end RS485 — no USB adapter needed.

## 兩條路徑 | Two paths

| 路徑 | 檔案 | 狀態 |
|---|---|---|
| **xArm SDK**（`getset_tgpio_modbus_data`）★ 可用 | `../lebai_gripper_xarm.py`, `demo_gripper.py` | **寫入可動夾爪**（write-only；讀取仍 timeout） |
| **xArmStudio WebSocket**（port 18333） | `studio_ws_gripper.py` | 同樣 write-only 可用 |

## 用法 | Usage

```bash
# SDK 路徑（firmware 正常時首選）
~/xarm-venv/bin/python ../lebai_gripper_xarm.py --ip 192.168.23.227 status
~/xarm-venv/bin/python demo_gripper.py
~/xarm-venv/bin/python scan_gripper.py            # 接線 debug 用

# Studio websocket 路徑
~/xarm-venv/bin/python studio_ws_gripper.py --ip 192.168.23.227 info
~/xarm-venv/bin/python studio_ws_gripper.py --ip 192.168.23.227 baud 115200
~/xarm-venv/bin/python studio_ws_gripper.py --ip 192.168.23.227 position 100
~/xarm-venv/bin/python studio_ws_gripper.py --ip 192.168.23.227 read 0x9C45
```

依賴 | Dependencies: `xarm`（xArm-Python-SDK）、`websocket-client`、
以及 parent dir 嘅 `lebai_gripper.py`（register map）。C++ probe 需要 build
xArm-CPLUS-SDK（`cpp_lebai_probe.cc` 頭部有編譯方法）。

## 調查記錄 | Investigation

見 **[FINDINGS.md](FINDINGS.md)** — firmware v2.7.1 下 SDK 路徑失效嘅完整排查記錄、
Studio websocket 協議逆向細節、error code 表。
