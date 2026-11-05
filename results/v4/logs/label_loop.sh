#!/bin/bash
# Labels finished v4 episodes with the primary judge every 10 minutes while the main run is going (resumable).
cd "$(dirname "$0")/../../.."
: "${PCB_CAP_OPENROUTER:?set PCB_CAP_OPENROUTER}"
while true; do
  .venv/bin/python scripts/label4.py --which primary runs/v4 --workers 6 >> results/v4/logs/label_primary.log 2>&1
  if ! pgrep -f "scripts/run.py --run v4 " > /dev/null; then
    .venv/bin/python scripts/label4.py --which primary runs/v4 --workers 6 >> results/v4/logs/label_primary.log 2>&1
    echo "LABEL LOOP DONE $(date)" >> results/v4/logs/status.log
    break
  fi
  sleep 600
done
