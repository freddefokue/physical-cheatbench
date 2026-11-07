"""File activity seen from the host (evaluator 4.3, PLAN_v4.md section 12, item 15).

The content watcher (common4.Task4.check_watched) compares a file between commands, so a file changed and put back
within one command left no trace, and a read of the examiner's table showed up only if its content reached a tool
output. This monitor uses inotify on the host side of the bind mounts: it keeps a copy of each watched file as it is
written, and counts reads of protected files. Reads by the cell itself (its checker, the content watcher) are muted.
Linux only; where inotify is missing it records nothing, and the scene behaves as evaluator 4.2.
"""
import ctypes
import os
import select
import struct
import threading
import time
from contextlib import contextmanager

IN_ACCESS, IN_MODIFY, IN_CLOSE_WRITE, IN_MOVED_TO = 0x1, 0x2, 0x8, 0x80
IN_CLOEXEC, IN_NONBLOCK = 0o2000000, 0o4000
MUTE_SLACK_S = 0.01                     # the event thread handles an event well within this after it occurs


class FileActivity:
    def __init__(self, reader):
        self.reader = reader            # sandbox path -> bytes or None, without following symlinks (Sandbox.read_file)
        self.lock = threading.Lock()
        self.events = []                # (monotonic t, sandbox path, "written" | "modified" | "read", bytes or None)
        self.dirs = {}                  # watch descriptor -> host directory
        self.files = {}                 # host path -> [sandbox path, {"write", "read"}]
        self.mutes = []                 # [t0, t1] windows of the cell's own reads
        self.stop = threading.Event()
        try:
            self.libc = ctypes.CDLL("libc.so.6", use_errno=True)
            self.fd = self.libc.inotify_init1(IN_CLOEXEC | IN_NONBLOCK)
        except (OSError, AttributeError):
            self.fd = -1
        self.thread = None
        if self.fd >= 0:
            self.thread = threading.Thread(target=self._loop, name="fswatch", daemon=True)
            self.thread.start()

    @property
    def active(self):
        return self.fd >= 0

    def watch(self, host_path, sandbox_path, kind):
        """kind "write": keep a copy of every write; "read": count reads."""
        if not self.active:
            return
        host_path = os.path.normpath(str(host_path))
        d = os.path.dirname(host_path)
        if d not in self.dirs.values():
            mask = IN_ACCESS | IN_MODIFY | IN_CLOSE_WRITE | IN_MOVED_TO
            wd = self.libc.inotify_add_watch(self.fd, d.encode(), mask)
            if wd < 0:
                return
            self.dirs[wd] = d
        self.files.setdefault(host_path, [sandbox_path, set()])[1].add(kind)

    @contextmanager
    def muted(self):
        """The cell's own reads of a protected file (its checker, the content watcher) are not the agent's."""
        w = [time.monotonic(), None]
        with self.lock:
            self.mutes.append(w)
        try:
            yield
        finally:
            w[1] = time.monotonic()

    def _is_muted(self, t):
        with self.lock:
            return any(t >= w[0] and (w[1] is None or t <= w[1] + MUTE_SLACK_S) for w in self.mutes)

    def _loop(self):
        while not self.stop.is_set():
            try:
                ready, _, _ = select.select([self.fd], [], [], 0.2)
            except (OSError, ValueError):
                return
            if not ready:
                continue
            try:
                buf = os.read(self.fd, 64 * 1024)
            except BlockingIOError:
                continue
            except OSError:
                return
            i = 0
            while i + 16 <= len(buf):
                wd, mask, _cookie, n = struct.unpack_from("iIII", buf, i)
                name = buf[i + 16:i + 16 + n].split(b"\0", 1)[0].decode("utf-8", "replace")
                i += 16 + n
                path = os.path.join(self.dirs.get(wd, ""), name)
                f = self.files.get(path)
                if f is None:
                    continue
                t = time.monotonic()
                sandbox_path, kinds = f
                if "write" in kinds and mask & (IN_CLOSE_WRITE | IN_MOVED_TO):
                    with self.muted():                          # a copy of what was written, taken straight away
                        try:
                            data = self.reader(sandbox_path)
                        except OSError:
                            data = None
                    with self.lock:
                        self.events.append((t, sandbox_path, "written", data))
                elif "write" in kinds and mask & IN_MODIFY:
                    with self.lock:
                        self.events.append((t, sandbox_path, "modified", None))
                elif "read" in kinds and mask & IN_ACCESS and not self._is_muted(t):
                    with self.lock:
                        self.events.append((t, sandbox_path, "read", None))

    def drain(self):
        """Events since the last drain, in order; and forget mute windows that have closed."""
        time.sleep(0.01)                                   # let the event thread catch up with the last command
        with self.lock:
            out, self.events = self.events, []
            now = time.monotonic()
            self.mutes = [w for w in self.mutes if w[1] is None or now - w[1] < 1.0]
        return out

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=1.0)
        if self.fd >= 0:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = -1
