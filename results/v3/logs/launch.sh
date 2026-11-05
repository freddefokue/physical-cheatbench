#!/bin/bash
# Launches the pre-registered v3 main run (PLAN_v3.md section 3): 9 models x 4 cells x 3 conditions x seeds 100-105.
# Detached and resumable: finished episodes are skipped, so a second launch reruns only exceptions and budget stops.
# PCB_CAP_OPENROUTER is the ledger total at launch plus the registered $130 (PLAN_v3.md section 10).
cd "$(dirname "$0")/../../.."
: "${PCB_CAP_OPENROUTER:?set PCB_CAP_OPENROUTER (ledger total at launch + 130)}"
export PCB_CAP_ANTHROPIC=0.51 PCB_CAP_OPENAI=8.34
M=opus-5.5,fable-5.1,gpt-6-sol,gpt-6-astra,gemini-3.8-flash,grok-4.7,deepseek-v4-pro,kimi-k3,muse-spark-1.3
E=leak_B,coat_B,assay_B,door_B
L=results/v3/logs
A="--run v3 --models $M --envs $E --seeds 100-105 --max-tool-calls 70 --max-cost 2.0"
.venv/bin/python scripts/run.py $A --condition att_pt --workers 8 >> $L/main_att_pt.log 2>&1 &
sleep 30
.venv/bin/python scripts/run.py $A --condition unatt_pt --workers 8 --skip-tests >> $L/main_unatt_pt.log 2>&1 &
.venv/bin/python scripts/run.py $A --condition unatt --workers 8 --skip-tests >> $L/main_unatt.log 2>&1 &
wait
echo "MAIN RUN FINISHED $(date)" >> $L/status.log
