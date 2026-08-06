"""Lebai (樂白) Gripper via xArm tool-end RS485 — no USB adapter needed
=====================================================================

Same API as ``lebai_gripper.LebaiGripper``, but the Modbus RTU frames are
tunnelled through the xArm SDK (``arm.getset_tgpio_modbus_data``) instead of
a local USB-RS485 dongle.

Wiring: plug the gripper's M8-8P cable into the xArm tool head connector
(24V 棕 / GND 綠 / 485A 橙 / 485B 藍 — same pinout as the xArm flange).

Usage (library):

    from lebai_gripper_xarm import LebaiGripperXArm

    with LebaiGripperXArm("192.168.23.227") as g:
        print(g.status())
        g.set_position(100)          # open fully
        g.wait_done(target=100)
        print(g.get_position())

Usage (CLI — same subcommands as lebai_gripper.py):

    python lebai_gripper_xarm.py --ip 192.168.23.227 status
    python lebai_gripper_xarm.py --ip 192.168.23.227 position 50

Note: position/force/speed values are 0-100 percentages, identical to the
serial version. Requires firmware with tool RS485 Modbus support
(tested on controller v2.7.1, xArm 6 / XI1300).
"""

from __future__ import annotations

import argparse
import sys
import time

from xarm.wrapper import XArmAPI

from lebai_gripper import Reg, GripperError  # shared register map


class LebaiGripperXArm:
    def __init__(
        self,
        ip: str,
        slave: int = 1,
        baudrate: int = 115200,
        host_id: int = 9,           # 9 = tool-end RS485, 11 = control-box RS485
        set_baud: bool = True,      # False if baud already configured
    ):
        self.ip = ip
        self.slave = slave
        self.baudrate = baudrate
        self.host_id = host_id
        self._set_baud = set_baud
        self.arm: XArmAPI | None = None

    # ------------------------------------------------------------------ conn
    def connect(self) -> None:
        self.arm = XArmAPI(self.ip)
        time.sleep(0.5)
        if self.arm.warn_code != 0:
            self.arm.clean_warn()
        if self.arm.error_code != 0:
            self.arm.clean_error()
        if self._set_baud:
            code = self.arm.set_tgpio_modbus_baudrate(self.baudrate)
            if code != 0:
                raise GripperError(f"set_tgpio_modbus_baudrate({self.baudrate}) failed, code={code}")
            time.sleep(2)  # bus re-initialises after baud change

    def close(self) -> None:
        if self.arm is not None:
            self.arm.disconnect()
            self.arm = None

    def __enter__(self) -> "LebaiGripperXArm":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ----------------------------------------------------------- modbus core
    def _exchange(self, pdu: list[int]) -> list[int]:
        """Send PDU (no CRC — controller adds it). Returns response bytes."""
        assert self.arm is not None, "not connected"
        if self.arm.error_code in (19, 111):  # stale RS485 timeout error
            self.arm.clean_error()
        code, ret = self.arm.getset_tgpio_modbus_data(pdu, host_id=self.host_id)
        if code != 0 or not ret:
            raise GripperError(
                f"Modbus exchange failed: code={code}, ret={ret}, "
                f"arm_err={self.arm.error_code} (bus silent — check wiring/power)")
        if ret[0] != self.slave:
            raise GripperError(f"response from unexpected slave {ret[0]}")
        if ret[1] & 0x80:
            raise GripperError(f"Modbus exception {ret[2]} for fc {pdu[1]:#x}")
        return ret

    def _read(self, reg: Reg) -> int:
        ret = self._exchange([
            self.slave, 0x03, int(reg) >> 8, int(reg) & 0xFF, 0x00, 0x01,
        ])
        # response: [addr, 0x03, byte_count(=2), hi, lo, (crc...)]
        if len(ret) < 5 or ret[2] != 0x02:
            raise GripperError(f"bad FC03 response for {reg:#06x}: {ret}")
        return (ret[3] << 8) | ret[4]

    def _write(self, reg: Reg, value: int) -> None:
        # doc examples use FC16 (0x10) write-multiple with quantity=1
        ret = self._exchange([
            self.slave, 0x10, int(reg) >> 8, int(reg) & 0xFF,
            0x00, 0x01, 0x02, int(value) >> 8, int(value) & 0xFF,
        ])
        # echo: [addr, 0x10, reg_hi, reg_lo, qty_hi, qty_lo, (crc...)]
        if len(ret) < 6 or ret[2] != (int(reg) >> 8) or ret[3] != (int(reg) & 0xFF):
            raise GripperError(f"bad FC10 echo for {reg:#06x}: {ret}")

    # ------------------------------------------------------------ write cmds
    @staticmethod
    def _pct(value: int, name: str = "value") -> int:
        value = int(value)
        if not 0 <= value <= 100:
            raise ValueError(f"{name} must be 0-100, got {value}")
        return value

    def set_position(self, value: int) -> None:
        """夾爪幅度 0(全合) - 100(全開)"""
        self._write(Reg.SET_POSITION, self._pct(value, "position"))

    def set_force(self, value: int) -> None:
        """夾爪力度 0-100"""
        self._write(Reg.SET_FORCE, self._pct(value, "force"))

    def set_speed(self, value: int) -> None:
        """開合速度 0-100（即時生效，斷電唔保存）"""
        self._write(Reg.SET_SPEED, self._pct(value, "speed"))

    def save_speed(self, value: int) -> None:
        """開合速度 0-100（斷電保存）"""
        self._write(Reg.SAVE_SPEED, self._pct(value, "speed"))

    def find_stroke(self) -> None:
        """找行程（初始化）"""
        self._write(Reg.FIND_STROKE, 1)

    def set_auto_find_stroke(self, mode: int) -> None:
        """1=關閉自動找行程, 2=關閉+斷電保存, 3=恢復+斷電保存"""
        if mode not in (1, 2, 3):
            raise ValueError("mode must be 1 (off), 2 (off+save) or 3 (restore+save)")
        self._write(Reg.AUTO_FIND_STROKE, mode)

    def set_address(self, new_address: int) -> None:
        """修改夾爪 Modbus 地址 1-10000（改完要用新地址通訊！）"""
        if not 1 <= int(new_address) <= 10000:
            raise ValueError("address must be 1-10000")
        self._write(Reg.SET_ADDRESS, int(new_address))

    # ------------------------------------------------------------- read cmds
    def get_position(self) -> int:
        """當前位置 0-100"""
        return self._read(Reg.CUR_POSITION)

    def get_torque(self) -> int:
        """當前力矩 0-100"""
        return self._read(Reg.CUR_TORQUE)

    def is_done(self) -> bool:
        """上一指令是否執行完"""
        return self._read(Reg.CMD_DONE) == 1

    def stroke_pending(self) -> bool:
        """True = 未找行程（需要先初始化）"""
        return self._read(Reg.STROKE_PENDING) == 1

    def wait_done(
        self,
        timeout: float = 15.0,
        poll: float = 0.1,
        target: int | None = None,
        tol: int = 2,
        stable_secs: float = 0.8,
    ) -> bool:
        """同 lebai_gripper.LebaiGripper.wait_done 邏輯（firmware quirk 兜底）。"""
        deadline = time.monotonic() + timeout
        last_pos: int | None = None
        stable_since: float | None = None
        while time.monotonic() < deadline:
            if self.is_done():
                return True
            if target is not None:
                pos = self.get_position()
                now = time.monotonic()
                if pos == last_pos:
                    if stable_since is None:
                        stable_since = now
                else:
                    stable_since = None
                last_pos = pos
                if stable_since is not None and now - stable_since >= stable_secs:
                    if abs(pos - target) <= tol or self.get_torque() > 0:
                        return True
            time.sleep(poll)
        raise TimeoutError(f"gripper still busy after {timeout}s")

    def status(self) -> dict:
        return {
            "position": self.get_position(),
            "torque": self.get_torque(),
            "cmd_done": self.is_done(),
            "stroke_pending": self.stroke_pending(),
        }


# ----------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Lebai gripper CLI via xArm tool RS485")
    p.add_argument("--ip", default="192.168.23.227", help="xArm controller IP")
    p.add_argument("--slave", type=int, default=1)
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--control-box", action="store_true",
                   help="use control-box RS485 (host_id=11) instead of tool-end (9)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p_pos = sub.add_parser("position"); p_pos.add_argument("value", type=int)
    p_f = sub.add_parser("force"); p_f.add_argument("value", type=int)
    p_s = sub.add_parser("speed"); p_s.add_argument("value", type=int)
    sub.add_parser("init")
    p_a = sub.add_parser("auto-init"); p_a.add_argument("mode", choices=["off", "off-save", "on-save"])
    args = p.parse_args(argv)

    host_id = 11 if args.control_box else 9
    with LebaiGripperXArm(args.ip, slave=args.slave, baudrate=args.baud, host_id=host_id) as g:
        if args.cmd == "status":
            for k, v in g.status().items():
                print(f"{k}: {v}")
        elif args.cmd == "position":
            g.set_position(args.value)
            g.wait_done(target=args.value)
            print(f"position -> {g.get_position()}")
        elif args.cmd == "force":
            g.set_force(args.value)
            print("force set")
        elif args.cmd == "speed":
            g.set_speed(args.value)
            print("speed set")
        elif args.cmd == "init":
            g.find_stroke()
            g.wait_done(timeout=30)
            print("find stroke done")
        elif args.cmd == "auto-init":
            mode = {"off": 1, "off-save": 2, "on-save": 3}[args.mode]
            g.set_auto_find_stroke(mode)
            print(f"auto find-stroke mode {mode} set")
    return 0


if __name__ == "__main__":
    sys.exit(main())
