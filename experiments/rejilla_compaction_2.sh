#!/usr/bin/env bash
# Segunda rejilla, EN SERIE: aviso declarado (sonda C) y guia de consulta (brazos *_lookup).
# Reanuda desde checkpoint: relanzar no repite episodios.
set -u
cd "$(dirname "$0")/.."
export PYTHONPATH="src;."
TODOS="summary fresh_lookup hybrid_lookup summary_lookup react skillstate"
LOOKUP="fresh_lookup hybrid_lookup summary_lookup"

python experiments/run_compaction.py --probe C --k 14 --seeds 17 6 10 --reps 2 \
  --client claude-cli --model claude-haiku-5-5 --arms $TODOS --aviso-declarado \
  --out results/compaction/C-haiku55-aviso || echo "FALLO C-haiku55-aviso"

python experiments/run_compaction.py --probe C --k 14 --seeds 17 6 10 --reps 2 \
  --client claude-cli --model claude-haiku-5-5 --arms $LOOKUP --aviso-declarado --guia-consulta \
  --out results/compaction/C-haiku55-aviso-guia || echo "FALLO C-haiku55-aviso-guia"

python experiments/run_compaction.py --probe A --k 40 --seeds 0 3 6 8 --reps 3 \
  --client claude-cli --model claude-haiku-5-5 --arms $LOOKUP --guia-consulta \
  --out results/compaction/A-haiku55-guia || echo "FALLO A-haiku55-guia"

python experiments/run_compaction.py --probe C --k 14 --seeds 17 6 10 --reps 2 \
  --client codex-cli --model gpt-6-luna --arms fresh_lookup hybrid_lookup --guia-consulta \
  --out results/compaction/C-luna6-guia || echo "FALLO C-luna6-guia"

echo "REJILLA 2 TERMINADA"
