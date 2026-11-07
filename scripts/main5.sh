#!/bin/bash
# The v5 main run (PLAN_v5.md sections 6 and 8), in the pre-registered order; resumable (--skip-done).
#   setsid nohup systemd-inhibit --what=idle:sleep:handle-lid-switch scripts/main5.sh > results/v5/logs/main5.log 2>&1 &
# The cap is read before every step from results/v5/cap.txt (the owner's cap for the project ledger, USD). A step whose
# estimated cost does not fit in what is left (cap minus settled spending, minus the judging still to come) is cut and
# logged, as section 8 pre-registers; the judges label every completed batch before the next step.
set -u
cd "$(dirname "$0")/.."
PY=.venv5/bin/python
MODELS=opus-5.5,fable-5.1,gpt-6-sol,gpt-6-astra,gemini-3.8-flash,grok-4.7,deepseek-v4-pro,kimi-k3,muse-spark-1.3
W=${PCB_WORKERS:-8}
LOG=results/v5/logs
mkdir -p $LOG

say() { echo "=== $(date '+%F %T') $*"; }
left() {   # USD left under the cap after settled spending
  $PY -c "from pcb import ledger; print(round(float(open('results/v5/cap.txt').read()) - ledger.spent('openrouter'), 2))"
}
# fits COST RESERVE: the step's estimate plus the judging it leaves for later must fit in what is left
fits() { $PY -c "import sys; sys.exit(0 if $(left) >= $1 + $2 else 1)"; }
run() {   # run NAME COST RESERVE COMMAND...
  local name=$1 cost=$2 reserve=$3; shift 3
  export PCB_CAP_OPENROUTER=$(cat results/v5/cap.txt)
  if fits "$cost" "$reserve"; then
    say "$name (estimate \$$cost, \$$(left) left of cap \$$PCB_CAP_OPENROUTER)"
    "$@"
  else
    say "CUT $name: estimate \$$cost + \$$reserve for judging does not fit in \$$(left) left (PLAN_v5.md section 8)"
  fi
}
label() { run "label $1" 2 0 $PY scripts/label5.py --which primary "${@:2}" --workers 8; \
          run "fallback $1" 1 0 $PY scripts/label5.py --which fallback "${@:2}" --workers 4; }

run main        44 9  $PY scripts/run5.py --models $MODELS --scenes guard,pack,leak --condition main --seeds 0-7 --workers $W --skip-done
label main runs/v5/main
run honest_ok   11 3  $PY scripts/run5.py --models $MODELS --scenes guard,pack,leak --condition honest_ok --seeds 0-1 --workers $W --skip-done
run authorized  11 3  $PY scripts/run5.py --models $MODELS --scenes guard,pack,leak --condition authorized --seeds 0-1 --workers $W --skip-done
label controls runs/v5/honest_ok runs/v5/authorized
run oracle      6 0   $PY scripts/run5.py --models $MODELS --scenes guard_oracle --condition main --seeds 0-3 --workers $W --skip-done
run v4agent     6 0   $PY scripts/run5_v4agent.py --models $MODELS --seeds 0-3 --workers $W --skip-done
run dont_cheat  22 5  $PY scripts/run5.py --models $MODELS --scenes guard,pack,leak --condition dont_cheat --seeds 0-3 --workers $W --skip-done
label dont_cheat runs/v5/dont_cheat
run sample 0 0 $PY scripts/label5.py --make-sample runs/v5/main runs/v5/dont_cheat runs/v5/honest_ok runs/v5/authorized
run independent 4 0 $PY scripts/label5.py --which independent --sample results/v5/labels/independent_sample.txt --workers 8
say done
