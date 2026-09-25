#!/usr/bin/env bash
# Efecto aislado del orden del prompt en el coste (revision adversarial 3, hallazgo 9).
# Stateful en Haiku, T=50, los dos ordenes marcando cache; solo cambia que va primero.
# 3 seeds x 2 tiradas por orden. Etiquetas ep1/ep2 (estado primero), hp1/hp2 (historia).
set -u
cd "$(dirname "$0")/.."
export ANTHROPIC_FOUNDRY_RESOURCE=${ANTHROPIC_FOUNDRY_RESOURCE:-rafae-m9snio9b-eastus2}
PY=.venv/bin/python
LOG=logs/orden_prompt.log
for s in 0 1 2; do
  for r in 1 2; do echo "$s ep$r estado_primero"; echo "$s hp$r historia_primero"; done
done | xargs -P 12 -n 3 bash -c '
  '"$PY"' experiments/adjudicar.py --horizon 50 --runtime stateful --seed "$0" \
    --etiqueta "$1" --stateful-orden "$2" --stateful-cache --model claude-haiku-4-5 \
    --provider foundry --max-tokens 8192 --apendice-b --sin-telemetria' >> "$LOG" 2>&1
echo "orden prompt terminada: $(date)" >> "$LOG"
