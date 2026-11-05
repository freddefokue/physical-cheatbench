#!/bin/bash
# Primary-judge labels for main-run episodes as they finish (resumable), then one final pass after the run.
cd "$(dirname "$0")/../../.."
export PCB_CAP_OPENROUTER=492.3
while [ "$(ps aux | grep 'scripts/run.py --run v3' | grep -v grep | wc -l)" -gt 0 ]; do
  .venv/bin/python scripts/label3.py --which primary runs/v3 --workers 6 >> results/v3/logs/label_primary.log 2>&1
  sleep 300
done
.venv/bin/python scripts/label3.py --which primary runs/v3 --workers 8 >> results/v3/logs/label_primary.log 2>&1
echo "LABEL LOOP FINISHED $(date -Is)" >> results/v3/logs/status.log
