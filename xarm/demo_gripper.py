"""Gripper open/close demo through the xArm tool RS485 (no arm motion).

    PYTHONPATH=../.venv/lib/python3.11/site-packages:.. \\
      ../.venv/bin/python demo_gripper.py [--ip 192.168.23.227]

On firmware v2.7.1 Modbus RX often times out, so this demo is write-only
(sleep between moves instead of wait_done / status reads).
"""
import argparse
import os
import sys
import time

# Prefer installed xArm SDK over this folder's name ("xarm/")
_SITE = os.path.join(os.path.dirname(__file__), "..", ".venv", "lib", "python3.11", "site-packages")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
if os.path.isdir(_SITE):
    sys.path.insert(0, os.path.abspath(_SITE))

from lebai_gripper_xarm import LebaiGripperXArm


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ip", default="192.168.23.227")
    p.add_argument("--slave", type=int, default=1)
    p.add_argument("--dwell", type=float, default=2.0, help="seconds between moves")
    args = p.parse_args()

    with LebaiGripperXArm(args.ip, slave=args.slave, write_only=True) as g:
        g.set_speed(80)
        g.set_force(50)
        time.sleep(0.3)

        print("open -> 100")
        g.set_position(100)
        time.sleep(args.dwell)

        print("close -> 0")
        g.set_position(0)
        time.sleep(args.dwell)

        print("mid -> 50")
        g.set_position(50)
        time.sleep(args.dwell)

        print("open -> 100")
        g.set_position(100)
        time.sleep(args.dwell)

        print("done (write-only — visually confirm motion)")


if __name__ == "__main__":
    main()
