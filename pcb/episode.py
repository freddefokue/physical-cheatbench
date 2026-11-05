"""Create and tear down one episode: task (simulated cell) + sandbox (workstation) + controller (socket server)."""
from .sandbox import Sandbox
from .server import CellServer
from .tasks.pins import PinsTask
from .tasks.markers import MarkersTask
from .tasks.dose import DoseTask
from .tasks.pallet import PalletTask

TASKS = {"pins": PinsTask, "markers": MarkersTask, "dose": DoseTask, "pallet": PalletTask}
ENVS = [("pins", "R"), ("pins", "D"), ("pins", "P"), ("markers", "D"), ("markers", "P"), ("dose", "D"), ("dose", "P")]
EXT_ENVS = [("pallet", "D"), ("pallet", "P")]          # safety extension (run after the main run)
ALL_ENVS = ENVS + EXT_ENVS


def env_id(task, variant):
    return f"{task}_{variant}"


class Episode:
    def __init__(self, task_name, variant, seed, ep_dir=None, condition="base"):
        self.task = TASKS[task_name](variant, seed, condition=condition)
        self.sb = Sandbox(self.task.mounts(), self.task.tools, hostname=f"{task_name}-ws")
        self.task.setup(self.sb)
        self.server = CellServer(self.task, str(self.sb.run_dir / "cell.sock"))

    def bash(self, command, timeout=180):
        out, rc, dt = self.sb.run(command, timeout=timeout)
        post = getattr(self.task, "after_command", None)
        if post:
            post()
        return out, rc, dt

    def close(self, keep_to=None):
        self.server.close()
        self.sb.cleanup(keep_to)
