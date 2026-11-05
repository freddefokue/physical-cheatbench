"""Operator workstation: a bubblewrap sandbox per episode (no network, only the episode's files are visible).

The episode directory holds the sandbox filesystem under fs/ (one subtree per mount) and the controller socket under
run/. Shell state does not persist between commands except the working directory, as in common agent harnesses.
"""
import os
import shutil
import signal
import stat
import subprocess
import time
import uuid
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parent / "client"
# Episode filesystems live under a neutral directory: anything inside the sandbox that shows host paths
# (/proc/self/mountinfo, findmnt) must not reveal the project, the run or the model.
WS_ROOT = Path.home() / ".ws"
HOME = "/home/robot"
CWD_MARK = "__WSH_PWD__"
MAX_OUTPUT = 8000          # characters returned to the agent per command (head and tail kept)


def truncate(text, limit=MAX_OUTPUT):
    if len(text) <= limit:
        return text
    head, tail = text[: limit // 2], text[-limit // 2:]
    return f"{head}\n... [{len(text) - limit} characters truncated] ...\n{tail}"


class Sandbox:
    """mounts: list of (sandbox_path, writable); each is backed by ep_dir/fs/<sandbox_path>."""

    def __init__(self, mounts, tools, hostname="cell-ws"):
        self.ep = WS_ROOT / uuid.uuid4().hex[:12]
        self.fs = self.ep / "fs"
        self.ep.mkdir(parents=True, exist_ok=True)
        self.run_dir = self.ep / "s"              # short path: Unix socket paths are limited to 108 bytes
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.mounts = [(HOME, True), ("/tmp", True), ("/opt/workcell", False)] + list(mounts)
        for p, _ in self.mounts:
            self.host(p).mkdir(parents=True, exist_ok=True)
        self.hostname = hostname
        self.cwd = HOME
        self._install_client(tools)
        etc = self.ep / "etc_base"
        etc.mkdir(exist_ok=True)
        (etc / "passwd").write_text("root:x:0:0:root:/root:/bin/bash\nrobot:x:1000:1000:Cell operator:/home/robot:/bin/bash\n")
        (etc / "group").write_text("root:x:0:\nrobot:x:1000:\n")
        (etc / "hostname").write_text(hostname + "\n")

    def host(self, sandbox_path):
        """Host path backing a sandbox path (only for paths under a mount)."""
        return self.fs / sandbox_path.lstrip("/")

    def _install_client(self, tools):
        opt = self.host("/opt/workcell")
        (opt / "bin").mkdir(parents=True, exist_ok=True)
        (opt / "lib").mkdir(parents=True, exist_ok=True)
        shutil.copy(CLIENT_DIR / "lib" / "workcell.py", opt / "lib" / "workcell.py")
        for t in tools:
            f = opt / "bin" / t
            f.write_text("#!/usr/bin/python3\nimport sys\nsys.path.insert(0, '/opt/workcell/lib')\n"
                         f"import workcell\nworkcell.cli({t!r})\n")
            f.chmod(0o755)

    def _argv(self, command):
        a = ["bwrap", "--clearenv", "--unshare-all", "--as-pid-1", "--die-with-parent", "--new-session", "--hostname", self.hostname,
             "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
             "--symlink", "usr/lib64", "/lib64", "--symlink", "usr/sbin", "/sbin",
             "--proc", "/proc", "--dev", "/dev",
             "--ro-bind", str(self.ep / "etc_base/passwd"), "/etc/passwd",
             "--ro-bind", str(self.ep / "etc_base/group"), "/etc/group",
             "--ro-bind", str(self.ep / "etc_base/hostname"), "/etc/hostname"]
        for p, writable in self.mounts:
            a += ["--bind" if writable else "--ro-bind", str(self.host(p)), p]
        a += ["--bind", str(self.run_dir), "/run/workcell"]
        env = {"HOME": HOME, "USER": "robot", "LOGNAME": "robot", "SHELL": "/bin/bash", "LANG": "C.UTF-8",
               "TERM": "dumb", "PATH": "/opt/workcell/bin:/usr/local/bin:/usr/bin:/bin",
               "PYTHONPATH": "/opt/workcell/lib", "PYTHONDONTWRITEBYTECODE": "1"}
        for k, v in env.items():
            a += ["--setenv", k, v]
        a += ["--chdir", HOME]
        script = (f"cd {self._q(self.cwd)} 2>/dev/null || cd {HOME}\n{command}\n__wsh_rc=$?\n"
                  f"printf '\\n{CWD_MARK}%s\\n' \"$PWD\"\nexit $__wsh_rc\n")
        return a + ["/bin/bash", "-c", script]

    @staticmethod
    def _q(s):
        return "'" + s.replace("'", "'\\''") + "'"

    def run(self, command, timeout=180):
        t0 = time.time()
        proc = subprocess.Popen(self._argv(command), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        timed_out = False
        try:
            out, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(proc.pid, signal.SIGKILL)
            out, _ = proc.communicate()
        text = out.decode("utf-8", errors="replace")
        lines = text.split("\n")
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].startswith(CWD_MARK):
                new = lines[i][len(CWD_MARK):].strip()
                if new:
                    self.cwd = new
                del lines[i]
                if i > 0 and lines[i - 1] == "":
                    del lines[i - 1]
                break
        text = "\n".join(lines).rstrip("\n")
        rc = proc.returncode
        if timed_out:
            text += f"\n[command timed out after {timeout} s and was killed]"
            rc = 124
        return text, rc, time.time() - t0

    # ---- host-side access to agent-controlled paths -------------------------------------------------------------
    # The controller runs on the host, outside the sandbox. Any path the agent can write (its home, /tmp, writable
    # mounts) may contain symlinks pointing anywhere on the host, so every host-side read or write of such a path walks
    # it one component at a time from the mount's host root with O_NOFOLLOW: a symlink in any component is refused,
    # and the walk cannot race with the agent swapping components.
    def _locate(self, sandbox_path):
        p = sandbox_path if str(sandbox_path).startswith("/") else os.path.join(self.cwd, str(sandbox_path))
        p = os.path.normpath(p)
        for mp, _ in sorted(self.mounts, key=lambda m: -len(m[0])):
            if p == mp or p.startswith(mp.rstrip("/") + "/"):
                parts = [x for x in os.path.relpath(p, mp).split("/") if x not in ("", ".")]
                return p, self.host(mp), parts
        return p, None, None

    def _open_beneath(self, sandbox_path, flags, mode=0o644, make_dirs=False):
        p, root, parts = self._locate(sandbox_path)
        if root is None or not parts or any(x == ".." for x in parts):
            raise PermissionError(f"path outside the workstation mounts: {p}")
        fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            for d in parts[:-1]:
                try:
                    nfd = os.open(d, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                except FileNotFoundError:
                    if not make_dirs:
                        raise
                    os.mkdir(d, 0o775, dir_fd=fd)
                    nfd = os.open(d, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
                os.close(fd)
                fd = nfd
            return os.open(parts[-1], flags | os.O_NOFOLLOW | os.O_CLOEXEC, mode, dir_fd=fd)
        finally:
            os.close(fd)

    def read_with_stat(self, sandbox_path, limit=8_000_000):
        """(bytes, stat) of a regular file, or (None, None) if missing, not regular, too big, or reached via a symlink."""
        try:
            fd = self._open_beneath(sandbox_path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            return None, None
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_size > limit:
                return None, None
            chunks, n = [], 0
            while True:
                b = os.read(fd, 1 << 20)
                if not b:
                    break
                chunks.append(b)
                n += len(b)
                if n > limit:
                    return None, None
            return b"".join(chunks), st
        finally:
            os.close(fd)

    def kind_of(self, sandbox_path):
        """'missing', 'file', 'symlink', 'dir' or 'other' for the last path component (never follows links)."""
        try:
            fd = self._open_beneath(sandbox_path, os.O_PATH)
        except FileNotFoundError:
            return "missing"
        except OSError:
            return "other"                                   # a symlinked parent directory, or unreadable
        try:
            m = os.fstat(fd).st_mode
            return ("symlink" if stat.S_ISLNK(m) else "file" if stat.S_ISREG(m) else "dir" if stat.S_ISDIR(m)
                    else "other")
        finally:
            os.close(fd)

    def read_bytes(self, sandbox_path, limit=8_000_000):
        return self.read_with_stat(sandbox_path, limit)[0]

    def write_bytes(self, sandbox_path, data, mode=0o644):
        """Write a file under a workstation mount, creating parent directories; refuses symlinks in the path."""
        fd = self._open_beneath(sandbox_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode, make_dirs=True)
        try:
            view = memoryview(data)
            while view:
                k = os.write(fd, view)
                view = view[k:]
        finally:
            os.close(fd)

    def read_file(self, sandbox_path):
        """Bytes of a file for view_image (resolved like the shell would, relative to the current directory)."""
        p, _, _ = self._locate(sandbox_path)
        return self.read_bytes(sandbox_path, limit=4_000_000), p

    def cleanup(self, keep_to=None):
        if keep_to:
            shutil.copytree(self.fs, Path(keep_to), dirs_exist_ok=True, symlinks=True)
        shutil.rmtree(self.ep, ignore_errors=True)
