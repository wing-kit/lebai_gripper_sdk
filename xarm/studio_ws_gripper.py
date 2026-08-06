"""xArmStudio websocket client for the tool RS485 bus (port 18333).

This is the SAME path xArmStudio's own RS485 debug page uses — useful when
the xArm SDK (getset_tgpio_modbus_data) does not work, e.g. firmware v2.7.1
(see FINDINGS.md).

Protocol (reverse-engineered from Studio's frontend JS):
  ws://<ip>:18333/ws?channel=prod&lang=en&v=1&id=<ms>
  -> {"cmd": "<name>", "data": {"userId": "", "version": "xarm7", ...}, "id": "<n>"}
  <- {"id": "<n>", "code": <code>, "data": ..., "type": "response"}
     code 100 = accepted (async result follows with same id)
     code 0   = ok, data.recv holds the reply hex
     code 1   = failed / bus timeout (only data.send echoed)

Commands:
    python studio_ws_gripper.py --ip 192.168.23.227 info
    python studio_ws_gripper.py --ip 192.168.23.227 baud 115200
    python studio_ws_gripper.py --ip 192.168.23.227 send "01 03 9C 45 00 01"
    python studio_ws_gripper.py --ip 192.168.23.227 read 0x9C45
    python studio_ws_gripper.py --ip 192.168.23.227 position 100
"""
import argparse
import json
import sys
import time

from websocket import create_connection


class StudioRS485:
    def __init__(self, ip: str, host_id: int = 9):
        url = "ws://{}:18333/ws?channel=prod&lang=en&v=1&id={}".format(
            ip, int(time.time() * 1000))
        self.ws = create_connection(url, timeout=10)
        self.host_id = host_id
        self._mid = 0

    def _call(self, cmd: str, data: dict | None = None, wait: float = 6):
        self._mid += 1
        mid = str(self._mid)
        self.ws.send(json.dumps({
            "cmd": cmd,
            "data": {"userId": "", "version": "xarm7", **(data or {})},
            "id": mid,
        }))
        got = []
        self.ws.settimeout(wait)
        deadline = time.time() + wait
        while time.time() < deadline:
            try:
                m = json.loads(self.ws.recv())
            except Exception:
                break
            if m.get("id") == mid:
                got.append(m)
                if len(got) >= 2:      # async result shares the same id
                    break
        return got

    def info(self) -> dict:
        r = self._call("xarm_get_end_io_info", {"host_id": self.host_id})
        if r and r[0].get("code") == 0:
            return r[0]["data"]
        raise RuntimeError(f"get_end_io_info failed: {r}")

    def set_baud(self, baud: int, timeout_ms: int = 1000) -> None:
        r = self._call("xarm_set_modbus_baud_rate", {
            "baudrate": baud, "host_id": self.host_id,
            "is_loop": False, "timeout": timeout_ms,
        })
        if not r or r[0].get("code") != 0:
            raise RuntimeError(f"set baud failed: {r}")
        time.sleep(2)

    def send_hex(self, hex_cmd: str, is_rtu: bool = True, timeout_s: int = 1):
        """Send one frame (Studio debug-panel semantics).

        hex_cmd: space-separated hex bytes WITHOUT CRC (controller adds it).
        Returns (code, recv_hex_or_None).
        """
        payload = {
            "host_id": self.host_id,
            "is_rtu": is_rtu,
            "is_run_cmd": True,
            "is_loop": False,
            "is_stop": True,
            "buadrate": 115200,      # (sic) Studio's own field name
            "timeout": timeout_s,
            "mdb_info": [{"checked": True, "note": {"cn": "", "en": ""},
                          "cmd": hex_cmd, "delay": 1000}],
        }
        r = self._call("xarm_set_effector_modbus_rtu_cmd", payload, wait=timeout_s + 6)
        code, recv = None, None
        for m in r:
            if m.get("code") in (0, 1) and m.get("data"):
                code = m["code"]
                recv = m["data"].get("recv")
        return code, recv

    # ------------------------------------------------------- Lebai helpers
    def read_reg(self, reg: int, slave: int = 1) -> int:
        code, recv = self.send_hex(
            "{:02X} 03 {:02X} {:02X} 00 01".format(slave, reg >> 8, reg & 0xFF))
        if code != 0 or not recv:
            raise RuntimeError(f"read {reg:#06x} failed (code={code}, recv={recv})")
        b = bytes(int(x, 16) for x in recv.split())
        return (b[3] << 8) | b[4]

    def write_reg(self, reg: int, value: int, slave: int = 1) -> None:
        """Write one register (FC16).

        On firmware v2.7.1 the gripper *does* move, but the controller often
        returns ``code=1`` with no ``recv`` (RX timeout). Treat that as
        fire-and-forget success for writes; reads still need a real reply.
        """
        code, recv = self.send_hex(
            "{:02X} 10 {:02X} {:02X} 00 01 02 {:02X} {:02X}".format(
                slave, reg >> 8, reg & 0xFF, value >> 8, value & 0xFF))
        if code == 0:
            return
        if code == 1 and recv is None:
            # TX reached the bus (motion confirmed) but no Modbus echo/RX
            return
        raise RuntimeError(f"write {reg:#06x}={value} failed (code={code})")

    def close(self):
        self.ws.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ip", default="192.168.23.227")
    p.add_argument("--control-box", action="store_true", help="host_id=11")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info")
    p_b = sub.add_parser("baud"); p_b.add_argument("value", type=int)
    p_s = sub.add_parser("send"); p_s.add_argument("hex")
    p_r = sub.add_parser("read"); p_r.add_argument("reg", type=lambda x: int(x, 0))
    p_w = sub.add_parser("write")
    p_w.add_argument("reg", type=lambda x: int(x, 0)); p_w.add_argument("val", type=int)
    p_p = sub.add_parser("position"); p_p.add_argument("value", type=int)
    args = p.parse_args(argv)

    s = StudioRS485(args.ip, host_id=11 if args.control_box else 9)
    try:
        if args.cmd == "info":
            d = s.info()
            print(f"baudrate={d.get('baudrate')} is_rtu={d.get('is_rtu')} timeout={d.get('timeout')}")
        elif args.cmd == "baud":
            s.set_baud(args.value)
            print("baud set ->", s.info().get("baudrate"))
        elif args.cmd == "send":
            print("code/recv:", s.send_hex(args.hex))
        elif args.cmd == "read":
            print(f"{args.reg:#06x} =", s.read_reg(args.reg))
        elif args.cmd == "write":
            s.write_reg(args.reg, args.val)
            print("written")
        elif args.cmd == "position":
            s.write_reg(0x9C40, args.value)
            print(f"position {args.value} commanded")
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
