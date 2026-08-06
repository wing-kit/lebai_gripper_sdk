"""
Lebai (樂白) Gripper SDK — Modbus RTU over RS485
=================================================

Protocol doc: 乐白夹爪通讯协议 V1
- RS485, 115200 8N1, Modbus RTU, default slave address 1
- Register addresses below are the RAW protocol addresses (0x9C4x),
  used as-is on the wire (see doc examples).

Usage (library):

    from lebai_gripper import LebaiGripper

    with LebaiGripper("/dev/modbus-gripper") as g:
        print(g.status())
        g.set_position(100)          # open fully
        g.wait_done(target=100)
        print(g.get_position())

Usage (CLI):

    python lebai_gripper.py status
    python lebai_gripper.py position 50
    python lebai_gripper.py force 30
    python lebai_gripper.py speed 80
    python lebai_gripper.py init            # find stroke
    python lebai_gripper.py auto-init off   # disable power-on auto find-stroke
"""

from __future__ import annotations

import argparse
import sys
import time
from enum import IntEnum

from pymodbus.client import ModbusSerialClient


class Reg(IntEnum):
    """Raw Modbus register addresses (function code 0x03 read / 0x10 write)."""

    SET_POSITION = 0x9C40        # 夾爪幅度控制 (W) 0-100
    SET_FORCE = 0x9C41           # 夾爪力度控制 (W) 0-100
    CUR_POSITION = 0x9C45        # 夾爪當前位置 (R) 0-100
    CUR_TORQUE = 0x9C46          # 夾爪當前力矩 (R) 0-100
    CMD_DONE = 0x9C47            # 指令是否執行完 (R) 1=done, 0=busy
    FIND_STROKE = 0x9C48         # 找行程指令 (W) 1
    STROKE_PENDING = 0x9C49      # 夾爪未找行程 (R) 1=pending, 0=found
    SET_SPEED = 0x9C4A           # 開合速度 (RW) 0-100
    SAVE_SPEED = 0x9C4B          # 開合速度斷電保存 (RW) 0-100
    AUTO_FIND_STROKE = 0x9C9A    # 1=off, 2=off+save, 3=restore+save (W)
    SET_ADDRESS = 0x9C9B         # 設定夾爪地址 (W) 1-10000


class GripperError(Exception):
    pass


class LebaiGripper:
    def __init__(
        self,
        port: str = "/dev/modbus-gripper",
        baudrate: int = 115200,
        slave: int = 1,
        timeout: float = 1.0,
    ):
        self.slave = slave
        self.client = ModbusSerialClient(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=timeout,
        )

    # ------------------------------------------------------------------ conn
    def connect(self) -> None:
        if not self.client.connect():
            raise GripperError(f"Cannot open serial port {self.client.comm_params.port}")

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "LebaiGripper":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _pct(value: int, name: str = "value") -> int:
        value = int(value)
        if not 0 <= value <= 100:
            raise ValueError(f"{name} must be 0-100, got {value}")
        return value

    def _read(self, reg: Reg) -> int:
        rr = self.client.read_holding_registers(address=int(reg), count=1, device_id=self.slave)
        if rr.isError():
            raise GripperError(f"Read 0x{int(reg):04X} failed: {rr}")
        return rr.registers[0]

    def _write(self, reg: Reg, value: int) -> None:
        # doc examples use function 0x10 (write multiple) with quantity=1
        rr = self.client.write_registers(address=int(reg), values=[int(value)], device_id=self.slave)
        if rr.isError():
            raise GripperError(f"Write 0x{int(reg):04X}={value} failed: {rr}")

    # ------------------------------------------------------------ write cmds
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
        """等到指令完成；TimeoutError 如果超時。

        完成條件（任一）:
        1. CMD_DONE flag = 1（韌體要求位置 *完全* 等於目標先會 set）
        2. 韌體 quirk 兜底：中間位置經常差 1 unit 唔 set flag（例如目標 50 停喺 49），
           所以傳入 target 時，位置穩定 stable_secs 秒、而且喺 target±tol 內，
           或者 torque>0（揾到嘢 / 頂住），都當完成。
        """
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
    p = argparse.ArgumentParser(description="Lebai gripper CLI")
    p.add_argument("--port", default="/dev/modbus-gripper")
    p.add_argument("--slave", type=int, default=1)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p_pos = sub.add_parser("position"); p_pos.add_argument("value", type=int)
    p_f = sub.add_parser("force"); p_f.add_argument("value", type=int)
    p_s = sub.add_parser("speed"); p_s.add_argument("value", type=int)
    sub.add_parser("init")
    p_a = sub.add_parser("auto-init"); p_a.add_argument("mode", choices=["off", "off-save", "on-save"])
    args = p.parse_args(argv)

    with LebaiGripper(port=args.port, slave=args.slave) as g:
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
