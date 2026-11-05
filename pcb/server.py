"""Cell controller: one per episode. Serves the in-sandbox client tools over a Unix socket and logs every call.

All cell logic lives in the task object (pcb/tasks/*.py); the server only parses requests, serialises access to the
task (the robot does one thing at a time) and records an event per call.
"""
import json
import os
import socket
import threading
import time
import traceback


class CellServer:
    def __init__(self, task, sock_path):
        self.task = task
        self.sock_path = sock_path
        self.lock = threading.Lock()
        self.events = []
        self._stop = threading.Event()
        if os.path.exists(sock_path):
            os.unlink(sock_path)
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(sock_path)
        os.chmod(sock_path, 0o777)
        self.sock.listen(16)
        self.sock.settimeout(0.5)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_conn, args=(conn,), daemon=True).start()

    def _handle_conn(self, conn):
        try:
            conn.settimeout(30)
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
            try:
                req = json.loads(buf.decode())
                argv = req.get("argv", [])
                if not isinstance(argv, list):
                    raise ValueError("argv must be a list")
                tool, argv = str(req.get("tool", "")), [str(a) for a in argv]
            except (ValueError, AttributeError, TypeError):      # malformed request: answer as an unknown tool
                tool, argv = "?", []
            with self.lock:
                t0 = self.task.clock
                try:
                    text, code, data = self.task.handle(tool, argv)
                except Exception:  # a bug in the task must not look like cell behaviour to the agent
                    tb = traceback.format_exc()
                    self.task.internal_errors.append(tb)
                    text, code, data = f"{tool}: internal controller error", 3, None
                self.events.append({"i": len(self.events), "wall": time.time(), "clock0": t0,
                                    "clock1": self.task.clock, "tool": tool, "argv": argv, "code": code,
                                    "text": text, "data": data})
            conn.sendall((json.dumps({"text": text, "code": code, "data": data}) + "\n").encode())
        except OSError:
            pass
        finally:
            conn.close()

    def close(self):
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
