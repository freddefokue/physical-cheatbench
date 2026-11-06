#!/bin/bash
# Rebalance of the v4 run's tail (PLAN_v4.md section 12, item 6): dont_cheat relaunched with 8 workers per process
# once main needed fewer. Same code and design as launch4.sh; resumable (finished episodes skipped).
cd "$(dirname "$0")/../../.."
: "${PCB_CAP_OPENROUTER:?set PCB_CAP_OPENROUTER}"
echo 500 > /proc/self/oom_score_adj            # under memory pressure the kernel kills a (resumable) run first
export PCB_CAP_ANTHROPIC=0.51 PCB_CAP_OPENAI=8.34 PCB_MIN_FREE_MB=2000 MALLOC_ARENA_MAX=2
E=spring_A,leak4_A,pack_A,guard_A,aloha_A,round_A
L=results/v4/logs
A="--run v4 --max-tool-calls 80 --max-cost 6.0 --skip-tests"
G1=opus-5.5,fable-5.1,gpt-6-sol; G2=gpt-6-astra,gemini-3.8-flash,grok-4.7; G3=deepseek-v4-pro,kimi-k3,muse-spark-1.3
.venv/bin/python scripts/run.py $A --models $G1,$G2 --envs $E --seeds 0-3 --condition dont_cheat --workers 8 >> $L/main_dont_cheat.log 2>&1 &
.venv/bin/python scripts/run.py $A --models $G3 --envs $E --seeds 0-3 --condition dont_cheat --workers 8 >> $L/main_dont_cheat_C.log 2>&1 &
wait
echo "DONT_CHEAT (launch5) PROCESSES EXITED $(date)" >> $L/status.log
