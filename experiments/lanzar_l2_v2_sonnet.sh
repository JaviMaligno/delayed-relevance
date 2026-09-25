#!/usr/bin/env bash
# Sonda L2 v2 en Sonnet 5 via Foundry, mismo diseno que Haiku: seeds 4/10/6, 8
# repeticiones, react y skillstate, tope 8192. Un proceso por seed y runtime.
set -u
cd "$(dirname "$0")/.."
export ANTHROPIC_FOUNDRY_RESOURCE=${ANTHROPIC_FOUNDRY_RESOURCE:-rafae-m9snio9b-eastus2}
export PYTHONPATH=src:.
LOG=logs/l2_v2_sonnet.log
for rt in react skillstate; do
  for s in 4 10 6; do
    .venv/bin/python experiments/diagnose_probeC.py --model claude-sonnet-5 --provider foundry \
      --runtimes $rt --seeds $s --repeats 8 --k 10 --max-tokens 8192 >> "$LOG" 2>&1 &
  done
done
wait
echo "l2 v2 sonnet terminada: $(date)" >> "$LOG"
