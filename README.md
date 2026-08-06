# Lebai Gripper SDK（樂白夾爪）

Modbus RTU（RS485, 115200 8N1）Python SDK，基於 `pymodbus`。
協議文件：樂白夾爪通訊協議 V1（見 Telegram 存檔 `.docx`）

## 安裝

```bash
cd ~/lebai_gripper_sdk
uv venv .venv
uv pip install --python .venv/bin/python pymodbus pyserial
# 或者直接用 uv run（自動裝依賴）：
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py status
```

## 硬件

- 裝置：`/dev/modbus-gripper`（udev rule: `99-modbus_gripper_usb.rules`，綁定 QinHeng 1a86:55d3 serial 5ACC051540）
- 夾爪需 **24V 供電**；RS485 A/B 線接好

## Library 用法

```python
from lebai_gripper import LebaiGripper

with LebaiGripper("/dev/modbus-gripper") as g:
    print(g.status())        # {'position':.., 'torque':.., 'cmd_done':.., 'stroke_pending':..}
    g.set_force(50)          # 力度 50%
    g.set_speed(80)          # 速度 80%
    g.set_position(100)      # 全開
    g.wait_done()            # 等執行完
    g.set_position(0)        # 全合
    g.wait_done()
```

## CLI

```bash
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py status
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py position 50
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py force 30
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py speed 80
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py init          # 找行程
uv run --no-project --with pymodbus --with pyserial lebai_gripper.py auto-init off # 關自動找行程
```

## API 對照（寄存器）

| 方法 | 寄存器 | 說明 |
|------|--------|------|
| `set_position(0-100)` | 0x9C40 W | 幅度（0=合, 100=開） |
| `set_force(0-100)` | 0x9C41 W | 力度 |
| `get_position()` | 0x9C45 R | 當前位置 |
| `get_torque()` | 0x9C46 R | 當前力矩 |
| `is_done()` | 0x9C47 R | 指令完成？ |
| `find_stroke()` | 0x9C48 W | 找行程 |
| `stroke_pending()` | 0x9C49 R | 未找行程？ |
| `set_speed(0-100)` | 0x9C4A RW | 速度（唔保存） |
| `save_speed(0-100)` | 0x9C4B RW | 速度（斷電保存） |
| `set_auto_find_stroke(1/2/3)` | 0x9C9A W | 1=關 2=關+保存 3=恢復+保存 |
| `set_address(1-10000)` | 0x9C9B W | 改 Modbus 地址（小心！） |
| `wait_done(timeout)` | — | 阻塞等 `is_done()` |
| `status()` | — | 一次過讀晒 |

## 診斷工具

`scan.py` — 自動掃描 slave address / baud rate 測試通訊（文件預設：slave 1, 115200 8N1）：

```bash
# 全自動掃描（slave 1-10 × 常見 baud）
uv run --no-project --with pymodbus --with pyserial scan.py

# 掃全部地址 1-247（慢）
uv run --no-project --with pymodbus --with pyserial scan.py --all-slaves

# 指定參數（可單獨指定 slave 或 baud）
uv run --no-project --with pymodbus --with pyserial scan.py --slave 1 --baud 115200
```

## 疑難

| 現象 | 查 |
|------|-----|
| `No response received`（所有地址/波特率都冇回應） | ① 夾爪 24V 供電有冇開 ② RS485 A/B 線係咪調轉咗（試調換）③ 轉接器係咪真 RS485（唔係 TTL） |
| `Cannot open serial port` | `ls -l /dev/modbus-gripper`；重插 USB |
| Permission denied | 用戶要在 `dialout` 群組（已設好） |

> ⚠️ 夾爪上電 5 秒後會**自動找行程**（會郁！），除非用 `auto-init off` 關咗。
