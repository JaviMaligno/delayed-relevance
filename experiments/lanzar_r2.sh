#!/usr/bin/env bash
# R2 del spec: Haiku 4.5 en T={50,200}, cuatro runtimes, 3 seeds x 8 repeticiones.
#
# Condiciones identicas a la Tabla 1 de Gemini -- entorno fiel (--apendice-b
# --sin-telemetria) y tope de salida 8192 -- porque comparar dos modelos con topes
# distintos es el error que ya costo una conclusion falsa (-5,8 puntos del Algoritmo 2).
#
# Cada episodio es un proceso aparte que escribe su traza y se SALTA si ya esta
# completa: la tanda es reanudable si se cae la sesion, la cuota o el portatil.
set -u
cd "$(dirname "$0")/.."
export ANTHROPIC_FOUNDRY_RESOURCE=${ANTHROPIC_FOUNDRY_RESOURCE:-rafae-m9snio9b-eastus2}
PY=.venv/bin/python
PARALELO=${PARALELO:-5}
LOG=logs/r2_haiku.log

for T in 50 200; do
  for runtime in react memory stateful skillstate; do
    for seed in 0 1 2; do
      for rep in h1 h2 h3 h4 h5 h6 h7 h8; do
        echo "$T $runtime $seed $rep"
      done
    done
  done
done | xargs -P "$PARALELO" -n 4 bash -c '
  '"$PY"' experiments/adjudicar.py --horizon "$0" --runtime "$1" --seed "$2" \
    --etiqueta "$3" --model claude-haiku-4-5 --provider foundry \
    --max-tokens 8192 --apendice-b --sin-telemetria
' >> "$LOG" 2>&1

echo "R2 terminada: $(date)" >> "$LOG"
