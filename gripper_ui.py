"""
Lebai Gripper SDK Demo — Tkinter UI
====================================

簡單圖形界面示範 SDK 功能：連接、狀態監察、位置 / 力度 / 速度控制、找行程。
Simple GUI demonstrating the SDK: connect, live status, position / force / speed
control, and find-stroke.

需要 tkinter（Ubuntu: sudo apt install python3-tk）。
Requires tkinter (Ubuntu: sudo apt install python3-tk).

用法 | Usage:
    uv run --no-project --with pymodbus --with pyserial gripper_ui.py
    # 或用 venv | or with the venv:
    .venv/bin/python gripper_ui.py
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

from lebai_gripper import GripperError, LebaiGripper

try:
    from pymodbus.exceptions import ModbusException
except ImportError:  # pragma: no cover - pymodbus 一定裝咗 | always installed with the SDK
    ModbusException = Exception

POLL_MS = 500          # 狀態刷新間隔 | status refresh interval
DEBOUNCE_MS = 250      # slider 拖動後幾耐先發指令 | delay after slider drag before sending


class GripperUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Lebai Gripper SDK Demo 樂白夾爪")
        root.minsize(520, 460)

        self.cmd_q: queue.Queue = queue.Queue()
        self.ui_q: queue.Queue = queue.Queue()
        self.connected = False
        self._pos_after_id: str | None = None

        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

        self._build()
        self._poll_status()
        self._drain_ui_queue()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}

        # --- 連接 Connection ---
        conn = ttk.LabelFrame(self.root, text="連接 Connection")
        conn.pack(fill="x", **pad)
        ttk.Label(conn, text="Port:").grid(row=0, column=0, sticky="e")
        self.port_var = tk.StringVar(value="/dev/modbus-gripper")
        ttk.Entry(conn, textvariable=self.port_var, width=22).grid(row=0, column=1)
        ttk.Label(conn, text="Slave:").grid(row=0, column=2, sticky="e")
        self.slave_var = tk.IntVar(value=1)
        ttk.Spinbox(conn, from_=1, to=247, textvariable=self.slave_var, width=5).grid(row=0, column=3)
        self.conn_btn = ttk.Button(conn, text="連接 Connect", command=self._toggle_connect)
        self.conn_btn.grid(row=0, column=4, padx=6)

        # --- 狀態 Status ---
        stat = ttk.LabelFrame(self.root, text="狀態 Status")
        stat.pack(fill="x", **pad)
        self.pos_lbl = ttk.Label(stat, text="位置 Position: —", width=20)
        self.tq_lbl = ttk.Label(stat, text="力矩 Torque: —", width=18)
        self.done_lbl = ttk.Label(stat, text="完成 Done: —", width=16)
        self.stroke_lbl = ttk.Label(stat, text="行程 Stroke: —", width=18)
        self.pos_lbl.grid(row=0, column=0, sticky="w")
        self.tq_lbl.grid(row=0, column=1, sticky="w")
        self.done_lbl.grid(row=0, column=2, sticky="w")
        self.stroke_lbl.grid(row=0, column=3, sticky="w")

        # --- 控制 Controls ---
        ctrl = ttk.LabelFrame(self.root, text="控制 Control")
        ctrl.pack(fill="x", **pad)

        self.pos_val = tk.IntVar(value=50)
        self.force_val = tk.IntVar(value=50)
        self.speed_val = tk.IntVar(value=80)

        self._slider_row(ctrl, 0, "位置 Position", self.pos_val,
                         on_release=lambda v: self._send("set_position", v), debounce=True)
        self._slider_row(ctrl, 1, "力度 Force", self.force_val,
                         on_release=lambda v: self._send("set_force", v))
        self._slider_row(ctrl, 2, "速度 Speed", self.speed_val,
                         on_release=lambda v: self._send("set_speed", v))

        btns = ttk.Frame(ctrl)
        btns.grid(row=3, column=0, columnspan=3, pady=6)
        ttk.Button(btns, text="全開 Open 100", command=lambda: self._goto(100)).pack(side="left", padx=4)
        ttk.Button(btns, text="全合 Close 0", command=lambda: self._goto(0)).pack(side="left", padx=4)
        ttk.Button(btns, text="找行程 Find Stroke", command=lambda: self._send("find_stroke")).pack(side="left", padx=4)

        # --- 日誌 Log ---
        logf = ttk.LabelFrame(self.root, text="日誌 Log")
        logf.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(logf, height=8, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

        self._log("未連接 Not connected")

    def _slider_row(self, parent, row, label, var, on_release, debounce=False):
        ttk.Label(parent, text=label, width=14).grid(row=row, column=0, sticky="e")
        val_lbl = ttk.Label(parent, text=str(var.get()), width=4)
        scale = ttk.Scale(parent, from_=0, to=100, variable=var,
                          command=lambda _: val_lbl.config(text=str(var.get())))
        scale.grid(row=row, column=1, sticky="ew", padx=4)
        parent.columnconfigure(1, weight=1)
        val_lbl.grid(row=row, column=2)

        def fire(_evt=None):
            on_release(var.get())

        if debounce:
            # 拖動完 DEBOUNCE_MS 後先發一次指令，避免狂轟串口
            # Send one command DEBOUNCE_MS after dragging stops, avoid flooding the bus
            def debounced(_evt=None):
                if self._pos_after_id:
                    self.root.after_cancel(self._pos_after_id)
                self._pos_after_id = self.root.after(DEBOUNCE_MS, fire)
            scale.bind("<ButtonRelease-1>", debounced)
            scale.bind("<KeyRelease>", debounced)
        else:
            scale.bind("<ButtonRelease-1>", fire)
            scale.bind("<KeyRelease>", fire)

    # -------------------------------------------------------------- actions
    def _toggle_connect(self) -> None:
        if self.connected:
            self.cmd_q.put(("disconnect",))
        else:
            self.cmd_q.put(("connect", self.port_var.get(), self.slave_var.get()))

    def _goto(self, value: int) -> None:
        self.pos_val.set(value)
        self._send("set_position", value)

    def _send(self, cmd: str, value: int | None = None) -> None:
        if not self.connected:
            self._log("⚠ 未連接 Not connected")
            return
        self.cmd_q.put((cmd, value))

    # ------------------------------------------------------------- worker
    def _worker_loop(self) -> None:
        g: LebaiGripper | None = None
        while True:
            try:
                msg = self.cmd_q.get(timeout=0.5)
            except queue.Empty:
                continue
            cmd = msg[0]
            try:
                if cmd == "connect":
                    _, port, slave = msg
                    # 短 timeout：裝置冇回應時快速失敗，唔會塞住指令隊列
                    # short timeout so a silent device fails fast and never jams the queue
                    g = LebaiGripper(port=port, slave=slave, timeout=0.3)
                    g.connect()
                    self.ui_q.put(("connected", True, f"已連接 Connected: {port} (slave {slave})"))
                elif cmd == "disconnect":
                    if g:
                        g.close()
                    g = None
                    self.ui_q.put(("connected", False, "已斷開 Disconnected"))
                elif cmd == "shutdown":
                    if g:
                        g.close()
                    return
                elif g is None:
                    self.ui_q.put(("log", "⚠ 未連接 Not connected"))
                elif cmd == "poll":
                    self.ui_q.put(("status", g.status()))
                elif cmd == "set_position":
                    g.set_position(msg[1])
                    self.ui_q.put(("log", f"→ set_position({msg[1]})"))
                elif cmd == "set_force":
                    g.set_force(msg[1])
                    self.ui_q.put(("log", f"→ set_force({msg[1]})"))
                elif cmd == "set_speed":
                    g.set_speed(msg[1])
                    self.ui_q.put(("log", f"→ set_speed({msg[1]})"))
                elif cmd == "find_stroke":
                    self.ui_q.put(("log", "→ find_stroke() 搵緊行程... finding stroke..."))
                    g.find_stroke()
                    g.wait_done(timeout=30)
                    self.ui_q.put(("log", "✓ 找行程完成 Find stroke done"))
            except (GripperError, TimeoutError, OSError, ModbusException) as e:
                # 瞬態通訊錯誤（例如夾爪郁緊冇回應）唔好殺死 worker，
                # log 低繼續 | transient bus errors (e.g. no response while moving)
                # must not kill the worker — log and keep going
                self.ui_q.put(("log", f"✗ {cmd} 失敗 failed: {e}"))

    # ---------------------------------------------------------- UI updates
    def _poll_status(self) -> None:
        # 隊列有嘢未處理就 skip 今次 poll，避免裝置冇回應時指令堆積
        # skip this tick if the queue is busy — prevents command pile-up on a silent device
        if self.connected and self.cmd_q.empty():
            self.cmd_q.put(("poll",))
        self._after_poll = self.root.after(POLL_MS, self._poll_status)

    def _drain_ui_queue(self) -> None:
        try:
            while True:
                msg = self.ui_q.get_nowait()
                kind = msg[0]
                if kind == "connected":
                    self.connected = msg[1]
                    self.conn_btn.config(text="斷開 Disconnect" if self.connected else "連接 Connect")
                    self._log(msg[2])
                elif kind == "status":
                    s = msg[1]
                    self.pos_lbl.config(text=f"位置 Position: {s['position']}")
                    self.tq_lbl.config(text=f"力矩 Torque: {s['torque']}")
                    self.done_lbl.config(text=f"完成 Done: {'✓' if s['cmd_done'] else '…'}")
                    self.stroke_lbl.config(text=f"行程 Stroke: {'pending!' if s['stroke_pending'] else 'OK'}")
                elif kind == "log":
                    self._log(msg[1])
        except queue.Empty:
            pass
        self._after_drain = self.root.after(50, self._drain_ui_queue)

    def _log(self, text: str) -> None:
        self.log.config(state="normal")
        self.log.insert("end", f"[{time.strftime('%H:%M:%S')}] {text}\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _on_close(self) -> None:
        # 取消 pending 嘅 after callbacks，避免 destroy 後 Tcl 報 invalid command name
        # cancel pending after callbacks so Tcl doesn't complain after destroy
        for aid in (getattr(self, "_after_poll", None), getattr(self, "_after_drain", None), self._pos_after_id):
            if aid:
                try:
                    self.root.after_cancel(aid)
                except tk.TclError:
                    pass
        self.cmd_q.put(("shutdown",))
        self.root.after(200, self.root.destroy)


def main() -> None:
    root = tk.Tk()
    GripperUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
