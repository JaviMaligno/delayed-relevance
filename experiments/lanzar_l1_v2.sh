#!/usr/bin/env bash
# Sonda L1 v2 (revision adversarial 5): runner que ya no repara el mundo en pasos sin
# accion, traza por paso. k=40, seeds 0-2 x 8, react y skillstate, cuatro condiciones
# (sin campo, notes, campo nombrado, recordatorio), tope 8192, los tres modelos.
set -u
cd "$(dirname "$0")/.."
export ANTHROPIC_FOUNDRY_RESOURCE=${ANTHROPIC_FOUNDRY_RESOURCE:-rafae-m9snio9b-eastus2}
export PYTHONPATH=src:.
PY=.venv/bin/python
LOG=logs/l1_v2.log
COMUN="--horizon 50 --seeds 3 --repeats 8 --ks 40 --only react skillstate --max-tokens 8192"
for m in claude-haiku-4-5 claude-sonnet-5; do
  for c in "" "--hatch-schema" "--oracle-schema" "--reminder"; do
    $PY experiments/probe_a.py $COMUN --model $m --provider foundry $c >> "$LOG" 2>&1 &
  done
done
# Gemini: dos procesos como maximo por la cuota de Vertex.
( for c in "" "--hatch-schema"; do
    $PY experiments/probe_a.py $COMUN --model gemini-3-flash-preview --provider vertex \
      --thinking-budget 0 $c >> "$LOG" 2>&1
  done ) &
( for c in "--oracle-schema" "--reminder"; do
    $PY experiments/probe_a.py $COMUN --model gemini-3-flash-preview --provider vertex \
      --thinking-budget 0 $c >> "$LOG" 2>&1
  done ) &
wait
echo "l1 v2 terminada: $(date)" >> "$LOG"
