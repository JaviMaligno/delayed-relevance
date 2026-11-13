#!/usr/bin/env bash
# Brazo fresh_ask (13-nov-2026), EN SERIE. Mismas condiciones que fresh_lookup en la
# sonda C coherente (sin guia ni aviso declarado) y en la sonda A sin guia. Antes de cada
# corrida espera a tener al menos 2,5 GB libres. Reanuda desde checkpoint.
set -u
cd "$(dirname "$0")/.."
export PYTHONPATH="src;."
C="--probe C --k 14 --seeds 17 6 10 --reps 2"
HAIKU="--client claude-cli --model claude-haiku-5-5"
R=results/compaction

espera_ram() {
  while true; do
    libre=$(powershell -NoProfile -c "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB,2)" | tr -d '\r' | tr ',' '.')
    echo "RAM libre: ${libre} GB"
    awk -v l="$libre" 'BEGIN{exit !(l >= 2.5)}' && return
    sleep 120
  done
}

espera_ram
python experiments/run_compaction.py $C $HAIKU --arms fresh_ask --aviso-coherente \
  --out $R/C-haiku55-coh-ask || echo "FALLO C-haiku55-coh-ask"
espera_ram
python experiments/run_compaction.py --probe A --k 40 --seeds 0 3 6 8 --reps 3 $HAIKU \
  --arms fresh_ask --out $R/A-haiku55-ask || echo "FALLO A-haiku55-ask"

echo "REJILLA ASK TERMINADA"
