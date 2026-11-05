#!/bin/bash
# Launches the pre-registered v2 runs (PLAN_v2.md section 2), detached; resumable (finished episodes are skipped).
cd "$(dirname "$0")/../../.."
export PCB_CAP_OPENROUTER=383.5 PCB_CAP_ANTHROPIC=0.51 PCB_CAP_OPENAI=8.34
M=opus-5.5,fable-5.1,gpt-6-sol,gpt-6-astra,gemini-3.8-flash,grok-4.7,deepseek-v4-pro,kimi-k3,muse-spark-1.3
L=results/v2/logs
.venv/bin/python scripts/run.py --run v2 --models $M --envs markers_P --condition base --seeds 10-19 --workers 4 >> $L/e1_base.log 2>&1 &
.venv/bin/python scripts/run.py --run v2 --models $M --envs markers_P,markers_D --condition fixed --seeds 10-19 --workers 6 >> $L/e1_fixed.log 2>&1 &
.venv/bin/python scripts/run.py --run v2 --models $M --envs markers_P --condition auth --seeds 10-19 --workers 4 >> $L/e1_auth.log 2>&1 &
.venv/bin/python scripts/run.py --run v2 --models $M --envs pallet_D,pallet_P --condition base --seeds 10-19 --workers 3 >> $L/e2_base.log 2>&1 &
.venv/bin/python scripts/run.py --run v2 --models $M --envs pallet_D,pallet_P --condition real --seeds 10-19 --workers 3 >> $L/e2_real.log 2>&1 &
wait
echo "ALL RUNS FINISHED" >> $L/status.log
