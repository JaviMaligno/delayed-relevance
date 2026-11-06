#!/usr/bin/env bash
# Segunda rejilla, EN SERIE. Sonda C con el aviso COHERENTE (corrige el pale que de
# verdad esta en la estanteria); guia de consulta en los brazos *_lookup; al final, el
# aviso ademas declarado en EVENT TYPES. Reanuda desde checkpoint.
set -u
cd "$(dirname "$0")/.."
export PYTHONPATH="src;."
TODOS="summary fresh_lookup hybrid_lookup summary_lookup react skillstate"
LOOKUP="fresh_lookup hybrid_lookup summary_lookup"
C="--probe C --k 14 --seeds 17 6 10 --reps 2"
HAIKU="--client claude-cli --model claude-haiku-5-5"
LUNA="--client codex-cli --model gpt-6-luna"
R=results/compaction

python experiments/run_compaction.py $C $HAIKU --arms $TODOS --aviso-coherente \
  --out $R/C-haiku55-coh || echo "FALLO C-haiku55-coh"
python experiments/run_compaction.py $C $HAIKU --arms $LOOKUP --aviso-coherente --guia-consulta \
  --out $R/C-haiku55-coh-guia || echo "FALLO C-haiku55-coh-guia"
python experiments/run_compaction.py --probe A --k 40 --seeds 0 3 6 8 --reps 3 $HAIKU \
  --arms $LOOKUP --guia-consulta --out $R/A-haiku55-guia || echo "FALLO A-haiku55-guia"
python experiments/run_compaction.py $C $LUNA --arms summary fresh_lookup hybrid_lookup \
  --aviso-coherente --out $R/C-luna6-coh || echo "FALLO C-luna6-coh"
python experiments/run_compaction.py $C $LUNA --arms fresh_lookup hybrid_lookup \
  --aviso-coherente --guia-consulta --out $R/C-luna6-coh-guia || echo "FALLO C-luna6-coh-guia"
python experiments/run_compaction.py $C $HAIKU --arms $TODOS --aviso-coherente --aviso-declarado \
  --out $R/C-haiku55-coh-aviso || echo "FALLO C-haiku55-coh-aviso"

echo "REJILLA 2 TERMINADA"
