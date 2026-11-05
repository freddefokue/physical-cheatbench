#!/bin/bash
# v3 pilot (development, before pre-registration): 4 models x 4 cells x 2 arms, one seed. Detached, resumable.
cd "$(dirname "$0")/../../.."
export PCB_CAP_OPENROUTER=363 PCB_CAP_ANTHROPIC=0.51 PCB_CAP_OPENAI=8.34
M=opus-5.5,gemini-3.8-flash,deepseek-v4-pro,gpt-6-sol
E=leak_B,coat_B,assay_B,door_B
L=results/v3/logs
.venv/bin/python scripts/run.py --run pilot_v3 --models $M --envs $E --condition att --seeds 100 --workers 8 --max-tool-calls 60 --max-cost 2.0 >> $L/pilot_att.log 2>&1 &
.venv/bin/python scripts/run.py --run pilot_v3 --models $M --envs $E --condition unatt --seeds 100 --workers 8 --max-tool-calls 60 --max-cost 2.0 --skip-tests >> $L/pilot_unatt.log 2>&1 &
wait
echo "PILOT FINISHED $(date)" >> $L/status.log
