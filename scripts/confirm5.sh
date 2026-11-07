#!/bin/bash
cd /home/fred/physical_cheatbench
export PCB_CAP_OPENROUTER=$(cat results/v5/cap.txt)
PY=.venv5/bin/python
echo "=== $(date '+%F %T') confirm: Astra main 200-203"
$PY scripts/search5.py --models gpt-6-astra --scenes teach_dev --condition main --seeds 200-203 --workers 2 --out runs/v5_confirm --budget 22.5 --skip-done
echo "=== $(date '+%F %T') confirm: Astra honest_ok 200-201"
$PY scripts/search5.py --models gpt-6-astra --scenes teach_dev --condition honest_ok --seeds 200-201 --workers 2 --out runs/v5_confirm --budget 22.5 --skip-done
echo "=== $(date '+%F %T') confirm: other models main 200"
$PY scripts/search5.py --models opus-5.5,fable-5.1,gpt-6-sol,gemini-3.8-flash,grok-4.7,deepseek-v4-pro,kimi-k3,muse-spark-1.3 --scenes teach_dev --condition main --seeds 200 --workers 2 --out runs/v5_confirm --budget 22.5 --skip-done
echo "=== $(date '+%F %T') confirm done"
