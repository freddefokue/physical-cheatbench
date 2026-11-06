#!/bin/bash
# The dont_cheat process was killed by the OOM killer at 11:41 (memory: about 0.45 GB per running episode, 26 running).
# Relaunch it once the honest_ok and authorized processes have finished and freed their memory. Resumable: finished
# episodes are skipped.
cd "$(dirname "$0")/../../.."
while kill -0 127957 2>/dev/null || kill -0 127958 2>/dev/null; do sleep 60; done
echo "relaunching dont_cheat $(date)" >> results/v4/logs/status.log
PCB_CAP_ANTHROPIC=0.51 PCB_CAP_OPENAI=8.34 .venv/bin/python scripts/run.py --run v4 \
  --models opus-5.5,fable-5.1,gpt-6-sol,gpt-6-astra,gemini-3.8-flash,grok-4.7,deepseek-v4-pro,kimi-k3,muse-spark-1.3 \
  --envs spring_A,leak4_A,pack_A,guard_A,aloha_A,round_A --seeds 0-3 --condition dont_cheat --workers 7 \
  --max-tool-calls 80 --max-cost 6.0 --skip-tests >> results/v4/logs/main_dont_cheat.log 2>&1
echo "dont_cheat process exited $(date)" >> results/v4/logs/status.log
