"""
Lebai gripper Modbus 診斷掃描工具
=================================

未指定參數時自動掃描常見組合；指定後只用該設定。
（文件預設值：slave 1, 115200 8N1 — 見 lebai_gripper.py）

用法：

    # 全自動掃描（slave 1-10 × 常見 baud rate）
    uv run --no-project --with pymodbus --with pyserial scan.py

    # 掃全部合法地址 1-247（慢！每個 baud 約 1-2 分鐘）
    uv run --no-project --with pymodbus --with pyserial scan.py --all-slaves

    # 指定 slave，掃 baud
    uv run --no-project --with pymodbus --with pyserial scan.py --slave 1

    # 指定 baud，掃 slave
    uv run --no-project --with pymodbus --with pyserial scan.py --baud 9600

    # 完全指定（文件預設）
    uv run --no-project --with pymodbus --with pyserial scan.py --slave 1 --baud 115200
"""

import argparse
import sys

from pymodbus.client import ModbusSerialClient

PROBE_REGISTER = 0x9C45          # 夾爪當前位置（可讀寄存器）
COMMON_BAUDS = [115200, 57600, 38400, 19200, 9600]
DEFAULT_SLAVE_SCAN = range(1, 11)   # 1-10
ALL_SLAVES = range(1, 248)          # 1-247


def probe(port, slave, baud, timeout=0.4):
    """試一次通訊；成功回傳位置值，失敗回傳 None。"""
    c = ModbusSerialClient(
        port=port, baudrate=baud, bytesize=8, parity="N", stopbits=1,
        timeout=timeout, retries=0,
    )
    try:
        c.connect()
        rr = c.read_holding_registers(address=PROBE_REGISTER, count=1, device_id=slave)
        if not rr.isError():
            return rr.registers[0]
    except Exception:
        pass
    finally:
        c.close()
    return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Lebai gripper Modbus scanner")
    p.add_argument("--port", default="/dev/modbus-gripper")
    p.add_argument("--slave", type=int, help="固定 slave 地址（唔俾就掃描）")
    p.add_argument("--baud", type=int, help="固定 baud rate（唔俾就掃描）")
    p.add_argument("--all-slaves", action="store_true", help="掃 1-247（慢）")
    args = p.parse_args(argv)

    bauds = [args.baud] if args.baud else COMMON_BAUDS
    if args.slave:
        slaves = [args.slave]
    elif args.all_slaves:
        slaves = ALL_SLAVES
    else:
        slaves = DEFAULT_SLAVE_SCAN

    print(f"Port: {args.port} | Slaves: {list(slaves)[:3]}...({len(list(slaves))} 個) "
          f"| Bauds: {bauds}")
    found = []
    for baud in bauds:
        for slave in slaves:
            pos = probe(args.port, slave, baud)
            if pos is not None:
                print(f"✅ FOUND  slave={slave}  baud={baud}  position={pos}")
                found.append((slave, baud))
            elif args.slave or slave % 50 == 0:
                print(f"… slave={slave} baud={baud} no response")
    if not found:
        print("\n❌ 搵唔到任何回應。檢查：24V 供電 / RS485 A-B 接線 / 轉接器")
        return 1
    print(f"\n總共搵到 {len(found)} 個組合")
    return 0


if __name__ == "__main__":
    sys.exit(main())
