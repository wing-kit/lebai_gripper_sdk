# Lebai Gripper SDK（樂白夾爪）

Modbus RTU（RS485, 115200 8N1）Python SDK，基於 `pymodbus`。
協議文件：樂白夾爪通訊協議 V1（`docs/` 內附有通訊協議及外接線文件）

Python SDK for the Lebai gripper over Modbus RTU (RS485, 115200 8N1), built on `pymodbus`.
Protocol reference: Lebai Gripper Communication Protocol V1 (protocol and external-wiring documents included under `docs/`).

---

## 安裝 | Installation

```bash
cd ~/lebai_gripper_sdk
uv venv .venv
uv pip install --python .venv/bin/python pymodbus pyserial
# 或者直接用 uv run（自動裝依賴）：
# or simply use uv run (dependencies resolved automatically):
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py status
```

## 硬件 | Hardware

- 裝置 | Device: `/dev/modbus-gripper`（udev rule: `99-modbus_gripper_usb.rules`，綁定 QinHeng 1a86:55d3 serial 5ACC051540）
- 夾爪需 **24V 供電**；RS485 A/B 線接好
- Gripper requires **24V power**; RS485 A/B lines connected

### 外接線對照 | External Wiring

> ⚠️ 待確認 — 原文件為圖像格式，暫未能提取；確認後補上。
> 接線前請核對，接錯 24V/RS485 可能損壞硬件。
>
> ⚠️ TBD — the source wiring document is image-based and could not be extracted reliably.
> Verify before wiring; incorrect 24V/RS485 connections may damage the hardware.

| 線色 Wire Color | 功能 Function | 接往 Connects To |
|------|------|------|
| 待補 TBD | 24V+ | 24V 電源正極 PSU + |
| 待補 TBD | GND | 24V 電源負極 PSU − |
| 待補 TBD | RS485 A (D+) | 轉接器 A Adapter A |
| 待補 TBD | RS485 B (D−) | 轉接器 B Adapter B |

## Library 用法 | Library Usage

```python
from lebai_gripper import LebaiGripper

with LebaiGripper("/dev/modbus-gripper") as g:
    print(g.status())        # {'position':.., 'torque':.., 'cmd_done':.., 'stroke_pending':..}
    g.set_force(50)          # 力度 50% | force 50%
    g.set_speed(80)          # 速度 80% | speed 80%
    g.set_position(100)      # 全開 | fully open
    g.wait_done()            # 等執行完 | wait until command completes
    g.set_position(0)        # 全合 | fully close
    g.wait_done()
```

## CLI

```bash
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py status
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py position 50
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py force 30
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py speed 80
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py init          # 找行程 | find stroke
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py auto-init off # 關自動找行程 | disable auto find-stroke
```

## API 對照（寄存器）| API & Register Map

| 方法 Method | 寄存器 Register | 說明 Description |
|------|--------|------|
| `set_position(0-100)` | 0x9C40 W | 幅度（0=合, 100=開）Position (0=close, 100=open) |
| `set_force(0-100)` | 0x9C41 W | 力度 Force |
| `get_position()` | 0x9C45 R | 當前位置 Current position |
| `get_torque()` | 0x9C46 R | 當前力矩 Current torque |
| `is_done()` | 0x9C47 R | 指令完成？Command complete? (1=yes) |
| `find_stroke()` | 0x9C48 W | 找行程 Find stroke (write 1) |
| `stroke_pending()` | 0x9C49 R | 未找行程？Stroke not yet found? (1=pending) |
| `set_speed(0-100)` | 0x9C4A RW | 速度（唔保存）Speed (not persisted) |
| `save_speed(0-100)` | 0x9C4B RW | 速度（斷電保存）Speed (persisted across power cycles) |
| `set_auto_find_stroke(1/2/3)` | 0x9C9A W | 1=關 off, 2=關+保存 off+save, 3=恢復+保存 restore+save |
| `set_address(1-10000)` | 0x9C9B W | 改 Modbus 地址（小心！）Change Modbus address (use with care!) |
| `wait_done(timeout)` | — | 阻塞等 `is_done()` Block until `is_done()` |
| `status()` | — | 一次過讀晒 Read all status at once |

## 診斷工具 | Diagnostics

`scan.py` — 自動掃描 slave address / baud rate 測試通訊（文件預設：slave 1, 115200 8N1）
Auto-scans slave address / baud rate (protocol defaults: slave 1, 115200 8N1):

```bash
# 全自動掃描（slave 1-10 × 常見 baud）| Full auto scan (slaves 1-10 × common baud rates)
uv run --no-project --with pymodbus --with pyserial scan.py

# 掃全部地址 1-247（慢）| Scan all addresses 1-247 (slow)
uv run --no-project --with pymodbus --with pyserial scan.py --all-slaves

# 指定參數（可單獨指定 slave 或 baud）| Specify slave and/or baud
uv run --no-project --with pymodbus --with pyserial scan.py --slave 1 --baud 115200
```

## 疑難 | Troubleshooting

| 現象 Symptom | 檢查 Check |
|------|-----|
| `No response received`（所有地址/波特率都冇回應 no response on any address/baud） | ① 夾爪 24V 供電 24V power on? ② RS485 A/B 線係咪調轉咗（試調換）A/B swapped? try swapping ③ 轉接器係咪真 RS485（唔係 TTL）adapter is real RS485, not TTL |
| `Cannot open serial port` | `ls -l /dev/modbus-gripper`；重插 USB replug USB |
| Permission denied | 用戶要在 `dialout` 群組 user must be in `dialout` group |

> ⚠️ 夾爪上電 5 秒後會**自動找行程**（會郁！），除非用 `auto-init off` 關咗。
> ⚠️ 5 seconds after power-on the gripper **automatically runs find-stroke** (it moves!), unless disabled via `auto-init off`.
