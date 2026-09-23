#!/usr/bin/env bash
# Re-medida de Stateful en Haiku con el parser v3 (revision adversarial 3, hallazgo 1):
# el v2 tiraba los parches escritos en Markdown en 7 de 15 episodios de T=200. Gemini no
# se re-mide: con v2 aplico 2.998 de 3.000. T={50,200}, 3 seeds x 5, etiquetas g1-g5.
set -u
cd "$(dirname "$0")/.."
export ANTHROPIC_FOUNDRY_RESOURCE=${ANTHROPIC_FOUNDRY_RESOURCE:-rafae-m9snio9b-eastus2}
PY=.venv/bin/python
LOG=logs/stateful_v3_haiku.log
for T in 200 50; do for s in 0 1 2; do for r in g1 g2 g3 g4 g5; do echo "$T $s $r"; done; done; done |
xargs -P 15 -n 3 bash -c '
  '"$PY"' experiments/adjudicar.py --horizon "$0" --runtime stateful --seed "$1" \
    --etiqueta "$2" --model claude-haiku-4-5 --provider foundry --max-tokens 8192 \
    --apendice-b --sin-telemetria' >> "$LOG" 2>&1
echo "stateful v3 haiku terminada: $(date)" >> "$LOG"
