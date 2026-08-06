# xArm 整合調查記錄 | xArm Integration Findings
（2026-08-06）

## 目標 | Goal

Lebai 夾爪由「PC + USB-RS485 轉接器」改為「**經 xArm 手腕 tool-end RS485**」控制
（夾爪 M8-8P 直插 xArm6 手腕接口，軟件經 xArm SDK 透傳 Modbus RTU frame）。

Drive the Lebai gripper through the xArm tool-end RS485 (host_id=9) instead
of a USB dongle.

## 環境 | Environment

- 手臂 | Arm: xArm 6（XI1300），controller firmware **v2.7.1**，IP 192.168.23.227
- xArm-Python-SDK **1.18.5**、xArm-CPLUS-SDK **1.18.1**
- 夾爪 | Gripper: Lebai，Modbus RTU slave 1 @ 115200 8N1（上電會自動 find-stroke，供電確認正常）

## 結論 | TL;DR

- **寫入可控制夾爪**（2026-08-06 用戶目視確認開/合/中位）：
  - **xArm SDK** `getset_tgpio_modbus_data` FC16 寫 `0x9C40` → 夾爪會動
    （API 仍回 code=3 / C19，全零 ret）
  - **Studio WebSocket** `xarm_set_effector_modbus_rtu_cmd` 同樣可動
    （code=1, recv=None）
- **讀取仍失敗**：FC03 讀 `0x9C45` 一律 timeout → **單向控制（write-only）**
- `lebai_gripper_xarm.py` 預設 `write_only=True`：寫入唔再因為冇 RX 而 raise
- 接線／供電 OK；TX 有上 bus，controller 對外 RX 路徑不可靠（firmware v2.7.1）

## 已排除嘅變數 | Variables Eliminated

| 變數 | 測試 | 結果 |
|---|---|---|
| Python SDK 層 | `getset_tgpio_modbus_data` RTU / TT / TT+503 | 全部 C19 |
| C++ SDK 層 | 同一函數（見 `cpp_lebai_probe.cc`） | 全部 C19 |
| Studio websocket | 1:1 複製（`studio_ws_gripper.py`），4 種 CRC/mode 組合 | 全部 code=1 冇 recv |
| A/B 極性 | 兩個方向都試過 | 都係靜默（其後 Studio 證明接線其實冇問題） |
| Baud rate | 115200/57600/38400/19200/9600 | 全部靜默 |
| Slave 地址 | 1-16 掃描 | 零回應 |
| CRC | 有/冇（controller 加 / frame 自帶） | 無分別 |
| 手臂狀態 | motion_enable + set_mode(0) + set_state(0) 後再試 | 無分別 |
| 控制箱 RS485 | host_id=11（baud set 回 code=22，呢部機可能冇控制箱 485 硬件） | C111 |

## Studio 內部協議（逆向）| Studio Internals (reverse-engineered)

xArmStudio 前端（controller 自帶 web server, port 18333）用 **plain WebSocket + JSON**：

```
ws://<ip>:18333/ws?channel=prod&lang=en&v=1&id=<ms>
→ {"cmd": "<name>", "data": {"userId": "", "version": "xarm7", ...}, "id": "<n>"}
← {"id": "<n>", "code": <code>, "data": ..., "type": "response"}
```

關鍵 command：
- `xarm_get_end_io_info` — 查 RS485 debug 狀態（**注意：debug 子系統 baud 預設 2000000**，同 SDK `set_tgpio_modbus_baudrate` 係兩個獨立設定）
- `xarm_set_modbus_baud_rate` — `{baudrate, host_id, is_loop, timeout}`
- `xarm_set_effector_modbus_rtu_cmd` — `{host_id, is_rtu, is_run_cmd, is_loop, is_stop, buadrate(係 typo 但係真欄位名), timeout, mdb_info:[{checked, note, cmd, delay}]}`
  - `cmd` 係空格分隔 hex string、**唔包 CRC**（preset 格式如此）
  - 回應 code：100=受理（異步）、0=成功（`data.recv` 有 hex）、1=失敗/bus timeout

Response code 1 時只有 `data.send` echo，冇 `recv` = 夾爪冇回應。

## Error code 備忘

- **C19** = tool-end RS485 通訊 timeout（controller 發咗嘢但收唔到回應）
- **C111** = 控制箱 RS485 通訊 timeout
- **API 22** = 參數唔支援（例如非標準 baud / 控制箱冇 485）
- **API 23** = Modbus 回應長度錯

## 下一步 | Next steps

1. **Chrome DevTools 捕獲**：F12 → Network → WS → Messages，喺 Studio send command，
   對照實際 JSON（確認欄位/參數同我哋複製嘅有咩出入）
2. 如果 DevTools 顯示 Studio 而家都失敗 → 硬件狀態改變，返去查物理層
3. 考慮 downgrade/upgrade controller firmware，或者向 UFACTORY 報告：
   v2.7.1 上 RS485_RTU(124)/RS485_AGENT(241) 外部命令失效但 Studio 內部可用

## 檔案 | Files in this folder

| 檔案 | 用途 |
|---|---|
| `../lebai_gripper_xarm.py` | xArm RS485 driver（SDK 路徑，firmware 正常時首選） |
| `demo_gripper.py` | 開合 demo（SDK 路徑） |
| `scan_gripper.py` | bus 掃描：5 baud × slave 1-16（SDK 路徑） |
| `studio_ws_gripper.py` | **Studio websocket 路徑** CLI：info / baud / send / read / write / position |
| `cpp_lebai_probe.cc` | C++ SDK probe 源碼 |
| `FINDINGS.md` | 呢份文件 |
