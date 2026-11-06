#!/bin/bash
# v3 pilot of the pointed-clue conditions (development, before pre-registration): 4 models x 4 cells x 2 arms, seed 101.
cd "$(dirname "$0")/../../.."
export PCB_CAP_OPENROUTER=372 PCB_CAP_ANTHROPIC=0.51 PCB_CAP_OPENAI=8.34
M=opus-5.5,gemini-3.8-flash,deepseek-v4-pro,gpt-6-sol
E=leak_B,coat_B,assay_B,door_B
L=results/v3/logs
.venv/bin/python scripts/run.py --run pilot_v3 --models $M --envs $E --condition unatt_pt --seeds 101 --workers 8 --max-tool-calls 70 --max-cost 2.0 >> $L/pilot_unatt_pt.log 2>&1 &
.venv/bin/python scripts/run.py --run pilot_v3 --models $M --envs $E --condition att_pt --seeds 101 --workers 8 --max-tool-calls 70 --max-cost 2.0 --skip-tests >> $L/pilot_att_pt.log 2>&1 &
wait
echo "PILOT_PT FINISHED $(date)" >> $L/status.log
