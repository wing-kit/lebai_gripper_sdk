"""Gripper open/close demo through the xArm tool RS485 (no arm motion).

    ~/xarm-venv/bin/python demo_gripper.py [--ip 192.168.23.227]

Uncomment the arm motion block for a minimal pick-and-place once the
gripper is responding.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lebai_gripper_xarm import LebaiGripperXArm


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ip", default="192.168.23.227")
    p.add_argument("--slave", type=int, default=1)
    args = p.parse_args()

    with LebaiGripperXArm(args.ip, slave=args.slave) as g:
        print("status:", g.status())

        if g.stroke_pending():
            print("stroke not found — running find_stroke()...")
            g.find_stroke()
            g.wait_done(timeout=30)

        g.set_speed(80)
        g.set_force(50)

        print("open -> 100")
        g.set_position(100)
        g.wait_done(target=100)
        print("position:", g.get_position())

        print("close -> 0")
        g.set_position(0)
        g.wait_done(target=0)
        print("position:", g.get_position(), "torque:", g.get_torque())

        # ---- optional arm motion (uncomment when ready) ----
        # arm = g.arm
        # arm.motion_enable(True)
        # arm.set_mode(0)
        # arm.set_state(0)
        # arm.set_position(x=300, y=0, z=200, roll=180, pitch=0, yaw=0,
        #                  speed=100, wait=True)


if __name__ == "__main__":
    main()
