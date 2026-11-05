#!/bin/bash
# Launches the pre-registered v4 main run (PLAN_v4.md section 6): 9 models x 6 scenes;
#   main seeds 0-7, dont_cheat seeds 0-3, honest_ok seeds 0-1, authorized (spring, aloha, round) seeds 0-1.
# Detached and resumable: finished episodes are skipped, so a second launch reruns only exceptions and budget stops.
# PCB_CAP_OPENROUTER is the ledger total at launch plus the registered v4 budget (PLAN_v4.md section 8).
cd "$(dirname "$0")/../../.."
: "${PCB_CAP_OPENROUTER:?set PCB_CAP_OPENROUTER (ledger total at launch + v4 budget)}"
export PCB_CAP_ANTHROPIC=0.51 PCB_CAP_OPENAI=8.34
M=opus-5.5,fable-5.1,gpt-6-sol,gpt-6-astra,gemini-3.8-flash,grok-4.7,deepseek-v4-pro,kimi-k3,muse-spark-1.3
E=spring_A,leak4_A,pack_A,guard_A,aloha_A,round_A
L=results/v4/logs
A="--run v4 --models $M --max-tool-calls 80 --max-cost 6.0"
.venv/bin/python scripts/run.py $A --envs $E --seeds 0-7 --condition main --workers 8 >> $L/main_main.log 2>&1 &
sleep 60
.venv/bin/python scripts/run.py $A --envs $E --seeds 0-3 --condition dont_cheat --workers 6 --skip-tests >> $L/main_dont_cheat.log 2>&1 &
.venv/bin/python scripts/run.py $A --envs $E --seeds 0-1 --condition honest_ok --workers 4 --skip-tests >> $L/main_honest_ok.log 2>&1 &
.venv/bin/python scripts/run.py $A --envs spring_A,aloha_A,round_A --seeds 0-1 --condition authorized --workers 3 --skip-tests >> $L/main_authorized.log 2>&1 &
wait
echo "MAIN RUN PROCESSES EXITED $(date)" >> $L/status.log
