# Setting up a server for Physical CheatBench

Checked on the laptop that ran v1–v5 (7 Nov 2026). Steps 0–6 prepare the machine; step 7 is a list of checks
that cost nothing. Run all of them before any paid run.

## 0. Before anything (the owner)
- **Revoke the five API keys that are in the old session transcript** at each provider: OpenAI, Anthropic, RunPod
  and both OpenRouter keys. Replacing them in `.env` doesn't invalidate the exposed copies.
- Create one new OpenRouter key for the server, **with a credit limit** set on the key.
- Create a GitHub fine-grained token for this repository only, with Contents and Pull requests set to read and
  write. The session opens pull requests; the owner merges them.
- Use a server with nothing else important on it: the agent will run commands without asking.

## 1. Machine
- Laptop baseline: Ubuntu 22.04, 8 cores, 15 GB of memory, Intel GPU. v5 ran 6–8 episodes at a time, each process
  using 0.6–1 GB. 12 heavy processes at once ran out of memory.
- For the same speed: at least 8 cores and 16 GB. With less, set fewer workers (`PCB_WORKERS`).
- Disk: about 3 GB (repository 0.5 GB, robot models 0.35 GB, Python environment about 1 GB, plus run logs).
- No GPU needed, but rendering then falls back to software (OSMesa) and is slower. Step 7a measures it.

## 2. System packages (Ubuntu)
```bash
sudo apt-get update
sudo apt-get install -y git tmux curl libgl1 libegl1 libglib2.0-0 libosmesa6
curl -LsSf https://astral.sh/uv/install.sh | sh        # the laptop had uv 0.9.5
# GitHub CLI: https://cli.github.com, then:
gh auth login            # with the fine-grained token
gh auth setup-git
```
`ffmpeg` is needed only for v4's visual demo (`scripts/demo4.py`).

## 3. Code
```bash
git clone https://github.com/freddefokue/physical-cheatbench.git ~/physical_cheatbench
cd ~/physical_cheatbench && git checkout handover      # v5 (55fc456) plus this folder
git clone https://github.com/robocurve/inspect-robots.git ~/src/inspect-robots
git -C ~/src/inspect-robots checkout 772019598e42ccc7921a043dee3a2ea2692020ea
```
Note that `main` doesn't contain v5 yet: PR #4 and PR #5 are open.

## 4. Python environment (Python 3.12.12, as on the laptop)
```bash
cd ~/physical_cheatbench
uv python install 3.12.12
uv venv .venv5 --python 3.12.12
uv pip install --python .venv5/bin/python -r handover/requirements-v5.txt
uv pip install --python .venv5/bin/python -e ~/src/inspect-robots -e ~/src/inspect-robots/plugins/inspect-robots-agent
```
v2–v4 used a separate `.venv` on Python 3.10. `.venv5` also runs the v4 code that v5 imports. Rebuild the old
environment only if you rerun v2–v4.

## 5. Robot models (MuJoCo Menagerie, the laptop's exact commit)
```bash
git clone --filter=blob:none --sparse https://github.com/google-deepmind/mujoco_menagerie.git ~/.cache/pcb/mujoco_menagerie
cd ~/.cache/pcb/mujoco_menagerie
git sparse-checkout set franka_emika_panda universal_robots_ur5e robotiq_2f85 aloha franka_fr3 i2rt_yam \
    unitree_go1 unitree_go2 unitree_g1 realsense_d435i
git checkout 98a70c569c4c1b6da467a20012f766ee1f8dc521
cd ~/physical_cheatbench
```
The code finds them at `~/.cache/pcb/mujoco_menagerie`; `PCB_MENAGERIE` overrides that path. v4's robot-dog scene
also needs `~/.cache/pcb/playground`: the Go1 model and policies from MuJoCo Playground, 1.7 MB. Copy that folder
from the laptop if you rerun v4; v5 doesn't need it. `~/.cache/pcb/src/robosuite` on the laptop is unused by the code.

## 6. Keys
Create `.env` in the repository root (it is gitignored) with one line:
```
OPENROUTER_API_KEY_2=<the new key>
```
v5 needs only this name. The v2–v4 code also reads `ANTHROPIC_API_KEY` and `OpenAI_API_KEY` (`pcb/providers.py`).
**Never `source .env`:** bash runs each line as a command, and on 4 Nov that printed every key into the session
log. The scripts load it with Python (`scripts/run5.py`, `load_env`).

## 7. Checks, in order (no API spend)
a. **Rendering** at v5's camera size (2560 × 1920):
   ```bash
   .venv5/bin/python handover/render_check.py                     # EGL (GPU)
   MUJOCO_GL=osmesa .venv5/bin/python handover/render_check.py    # software fallback
   ```
   Laptop: EGL, 0.03–0.08 s per frame. If only OSMesa works, `export MUJOCO_GL=osmesa` for every run
   (`pcb/sim/core.py` defaults to `egl`), and note the time per frame.

b. **Tests:** `.venv5/bin/python -m pytest -q`. Laptop: 101 passed, 5 warnings, 50 s.

c. **Scripted validation** (scripted agents through the same tools, no model calls):
   ```bash
   .venv5/bin/python scripts/validate5.py --scenes guard --seeds 0 --out validation_server.json
   ```
   Laptop: 83 s, about 1 GB peak, with all four routes identical to `results/v5/validation.json` (8 of 10 packed
   honestly in the main condition, both shortcuts pass the check and are logged). Always pass `--out` with a new
   name: the default overwrites the committed `results/v5/validation.json`. Then run all scenes:
   `--scenes guard,pack,leak --seeds 0-7`.

d. **Only then a paid pilot,** with the owner's go-ahead. The ledger (`results/ledger.jsonl`, all versions) stands
   at $974.97 of OpenRouter spending against the $994.64 cap in `results/v5/cap.txt` (7 Nov). It also holds $5.30 of
   open reservations left by killed calls; reconcile them before relying on the headroom. Only the owner raises the
   cap, and `scripts/main5.sh` checks it before each step. Reconcile spending against OpenRouter with
   `scripts/reconcile_ledger.py`.

## 8. Long jobs
- Run Claude Code itself inside `tmux` (`tmux new -s pcb`; detach with Ctrl-b d; `tmux attach -t pcb`), so it keeps
  running when you disconnect.
- Run experiment drivers detached too, and size `PCB_WORKERS` (default 8 in `scripts/main5.sh`) to memory: about
  1 GB per episode plus 2–3 GB spare.
- Kill by PID or with a bracketed pattern (`pkill -f "[v]alidate5"`): a plain `pkill -f pattern` also matches the
  shell that runs it.

## 9. What stays on the laptop
- The framework logs (`runs/v5*/**/*.inspect.tar.gz`, 527 files, about 554 MB) with the camera images each model
  saw. Copy them with `rsync` only if the next study needs them.
- Branch `v4-demo` (v4's visual demo, never pushed).
- Untracked v3 drafts (`RESULTS_v3.md`, `results/v3/summary.json`, `results/v3/tables.md`).
- The reviewer's audit scripts and evidence in `~/pais/review` (the review texts are in `handover/reviews/`).
- The old Claude Code transcript and `~/.claude`: **don't copy them.** The transcript holds the exposed keys, and
  the memory notes mix old conclusions with retractions.
