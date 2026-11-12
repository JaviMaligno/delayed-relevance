#!/usr/bin/env bash
# Repeticion del bloque 1 (sonda L2 v2, la del 93/93 frente a 18/82 de SKILL.state) con el
# aviso coherente. Mismas condiciones que lanzar_l2_v2.sh (Haiku 4.5, seeds 4/10/6, k=10,
# tope 8192, react y skillstate) salvo el cliente: claude -p por suscripcion en vez de
# Foundry. Por eso va tambien el aviso viejo con el mismo cliente: el cambio de arnes no
# debe leerse como efecto del aviso. En serie (la maquina se queda sin memoria) y
# reanudable: lo ya hecho se salta.
set -u
cd "$(dirname "$0")/.."
export PYTHONPATH="src;."
OUT=results/bloque1-coherente
REPS=${REPS:-4}
MODEL=${MODEL:-claude-haiku-4-5}
COMUN="--model $MODEL --provider claude-cli --seeds 4 10 6 --repeats $REPS --k 10 --max-tokens 8192 --out $OUT"
for rt in skillstate react; do
  python experiments/diagnose_probeC.py $COMUN --runtimes $rt --aviso-coherente || exit 1
done
for rt in skillstate react; do
  python experiments/diagnose_probeC.py $COMUN --runtimes $rt || exit 1
done
echo "BLOQUE 1 COHERENTE TERMINADO $(date)"
