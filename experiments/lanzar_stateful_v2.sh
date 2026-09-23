#!/usr/bin/env bash
# Re-medida de Stateful con el parser arreglado (opcion B): T={50,200}, 15 tiradas por
# celda, en las mismas condiciones que su tabla. Haiku 3 seeds x 5 (etiquetas f1-f5),
# Gemini 5 seeds x 3 (f1-f3), como el protocolo de cada modelo. Reanudable.
set -u
cd "$(dirname "$0")/.."
export ANTHROPIC_FOUNDRY_RESOURCE=${ANTHROPIC_FOUNDRY_RESOURCE:-rafae-m9snio9b-eastus2}
PY=.venv/bin/python
LOG=logs/stateful_v2.log

haiku() {
  for T in 50 200; do for s in 0 1 2; do for r in f1 f2 f3 f4 f5; do echo "$T $s $r"; done; done; done |
  xargs -P 15 -n 3 bash -c '
    '"$PY"' experiments/adjudicar.py --horizon "$0" --runtime stateful --seed "$1" \
      --etiqueta "$2" --model claude-haiku-4-5 --provider foundry --max-tokens 8192 \
      --apendice-b --sin-telemetria'
}

gemini() {
  # Dos procesos como maximo: tres agotan la cuota de Vertex y matan corridas pagadas.
  for T in 200 50; do for s in 0 1 2 3 4; do for r in f1 f2 f3; do echo "$T $s $r"; done; done; done |
  xargs -P 2 -n 3 bash -c '
    '"$PY"' experiments/adjudicar.py --horizon "$0" --runtime stateful --seed "$1" \
      --etiqueta "$2" --model gemini-3-flash-preview --provider vertex --max-tokens 8192 \
      --thinking-budget 0 --apendice-b --sin-telemetria'
}

haiku >> "$LOG" 2>&1 &
gemini >> "$LOG" 2>&1 &
wait
echo "stateful v2 terminada: $(date)" >> "$LOG"
