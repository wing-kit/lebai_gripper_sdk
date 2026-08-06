"""Full matrix scan: find the gripper on the xArm tool RS485 bus.

Scans 5 common baud rates x slave addresses 1-16 via the arm's tool-end
RS485 (host_id=9). Prints any responding combination.

    ~/xarm-venv/bin/python scan_gripper.py [--ip 192.168.23.227] [--control-box]
"""
import argparse
import time

from xarm.wrapper import XArmAPI

PROBE_REG = 0x9C45  # CUR_POSITION — always readable on a live gripper


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--ip", default="192.168.23.227")
    p.add_argument("--control-box", action="store_true",
                   help="scan control-box RS485 (host_id=11) instead of tool-end")
    args = p.parse_args()
    host_id = 11 if args.control_box else 9

    arm = XArmAPI(args.ip)
    time.sleep(0.5)
    arm.set_tgpio_modbus_timeout(400)

    found = []
    for baud in [115200, 9600, 57600, 38400, 19200]:
        arm.set_tgpio_modbus_baudrate(baud)
        time.sleep(2)
        for slave in range(1, 17):
            if arm.error_code:
                arm.clean_error()
            _, ret = arm.getset_tgpio_modbus_data(
                [slave, 0x03, PROBE_REG >> 8, PROBE_REG & 0xFF, 0x00, 0x01],
                host_id=host_id)
            if any(ret):
                print(f"✅ HIT baud={baud} slave={slave}: {ret[:8]}", flush=True)
                found.append((baud, slave))
        print(f"baud={baud} done", flush=True)

    arm.set_tgpio_modbus_baudrate(115200)  # restore default
    arm.disconnect()
    if not found:
        print("\n❌ bus silent — check 485A/B wiring, common GND, connector seating")
        return 1
    print(f"\nFOUND: {found}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
