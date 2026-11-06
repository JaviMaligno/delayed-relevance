#!/usr/bin/env bash
# Rejilla completa del experimento de compactacion, EN SERIE (la maquina se satura).
# Cada corredor reanuda desde su checkpoint, asi que relanzar este script no repite episodios.
set -u
cd "$(dirname "$0")/.."
export PYTHONPATH="src;."   # sin esto importa el paquete del arbol principal
ARMS_TODOS="summary fresh_lookup hybrid_lookup summary_lookup react skillstate"

python experiments/run_compaction.py --probe C --k 14 --seeds 17 6 10 --reps 2 \
  --client claude-cli --model claude-haiku-5-5 --arms $ARMS_TODOS \
  --out results/compaction/C-haiku55 || echo "FALLO C-haiku55"

python experiments/run_compaction.py --probe C --k 14 --seeds 17 6 10 --reps 2 \
  --client codex-cli --model gpt-6-luna --arms summary fresh_lookup hybrid_lookup \
  --out results/compaction/C-luna6 || echo "FALLO C-luna6"

python experiments/run_compaction.py --probe A --k 40 --seeds 0 3 6 8 --reps 3 \
  --client claude-cli --model claude-haiku-5-5 --arms $ARMS_TODOS \
  --out results/compaction/A-haiku55 || echo "FALLO A-haiku55"

echo "REJILLA TERMINADA"
