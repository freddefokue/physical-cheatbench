"""Operator workstation: a bubblewrap sandbox per episode (no network, only the episode's files are visible).

The episode directory holds the sandbox filesystem under fs/ (one subtree per mount) and the controller socket under
run/. Shell state does not persist between commands except the working directory, as in common agent harnesses.
"""
import os
import shutil
import signal
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

    def read_file(self, sandbox_path):
        """Resolve a sandbox path (relative to the current directory) to a host file, for view_image."""
        p = sandbox_path if sandbox_path.startswith("/") else os.path.normpath(os.path.join(self.cwd, sandbox_path))
        p = os.path.normpath(p)
        for mp, _ in sorted(self.mounts, key=lambda m: -len(m[0])):
            if p == mp or p.startswith(mp.rstrip("/") + "/"):
                h = self.host(mp) / os.path.relpath(p, mp)
                if h.is_file():
                    return h.read_bytes(), p
                return None, p
        return None, p

    def cleanup(self, keep_to=None):
        if keep_to:
            shutil.copytree(self.fs, Path(keep_to), dirs_exist_ok=True)
        shutil.rmtree(self.ep, ignore_errors=True)
