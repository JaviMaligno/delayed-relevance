#!/usr/bin/env bash
# Sonda L2 v2 (revision adversarial 5, hallazgo 1): seeds 4/10/6, 8 repeticiones, react
# y skillstate, con las condiciones de la Tabla 1 (tope 8192; Gemini con presupuesto de
# razonamiento 0). Haiku en paralelo por seed y runtime; Gemini con dos procesos como
# maximo, por la cuota de Vertex.
set -u
cd "$(dirname "$0")/.."
export ANTHROPIC_FOUNDRY_RESOURCE=${ANTHROPIC_FOUNDRY_RESOURCE:-rafae-m9snio9b-eastus2}
export PYTHONPATH=src:.
PY=.venv/bin/python
LOG=logs/l2_v2.log
for rt in react skillstate; do
  for s in 4 10 6; do
    $PY experiments/diagnose_probeC.py --model claude-haiku-4-5 --provider foundry \
      --runtimes $rt --seeds $s --repeats 8 --k 10 --max-tokens 8192 >> "$LOG" 2>&1 &
  done
done
for rt in react skillstate; do
  $PY experiments/diagnose_probeC.py --model gemini-3-flash-preview --provider vertex \
    --runtimes $rt --seeds 4 10 6 --repeats 8 --k 10 --max-tokens 8192 \
    --thinking-budget 0 >> "$LOG" 2>&1 &
done
wait
echo "l2 v2 terminada: $(date)" >> "$LOG"
