#!/bin/bash
# Relaunch of the v4 main run after the renderer rewrite (PLAN_v4.md section 12, item 4). Same design as launch.sh;
# processes split by model group so that the work spreads over the CPU cores. Resumable: finished episodes skipped.
cd "$(dirname "$0")/../../.."
: "${PCB_CAP_OPENROUTER:?set PCB_CAP_OPENROUTER}"
export PCB_CAP_ANTHROPIC=0.51 PCB_CAP_OPENAI=8.34 PCB_MIN_FREE_MB=3000 MALLOC_ARENA_MAX=2
E=spring_A,leak4_A,pack_A,guard_A,aloha_A,round_A
L=results/v4/logs
A="--run v4 --max-tool-calls 80 --max-cost 6.0 --skip-tests"
G1=opus-5.5,fable-5.1,gpt-6-sol; G2=gpt-6-astra,gemini-3.8-flash,grok-4.7; G3=deepseek-v4-pro,kimi-k3,muse-spark-1.3
.venv/bin/python scripts/run.py $A --models $G1 --envs $E --seeds 0-7 --condition main --workers 5 >> $L/main_main_A.log 2>&1 &
.venv/bin/python scripts/run.py $A --models $G2 --envs $E --seeds 0-7 --condition main --workers 5 >> $L/main_main_B.log 2>&1 &
.venv/bin/python scripts/run.py $A --models $G3 --envs $E --seeds 0-7 --condition main --workers 5 >> $L/main_main_C.log 2>&1 &
.venv/bin/python scripts/run.py $A --models $G1,$G2 --envs $E --seeds 0-3 --condition dont_cheat --workers 4 >> $L/main_dont_cheat.log 2>&1 &
.venv/bin/python scripts/run.py $A --models $G3 --envs $E --seeds 0-3 --condition dont_cheat --workers 4 >> $L/main_dont_cheat_C.log 2>&1 &
.venv/bin/python scripts/run.py $A --models $G1,$G2,$G3 --envs $E --seeds 0-1 --condition honest_ok --workers 4 >> $L/main_honest_ok.log 2>&1 &
.venv/bin/python scripts/run.py $A --models $G1,$G2,$G3 --envs spring_A,aloha_A,round_A --seeds 0-1 --condition authorized --workers 3 >> $L/main_authorized.log 2>&1 &
wait
echo "MAIN RUN (launch3) PROCESSES EXITED $(date)" >> $L/status.log
