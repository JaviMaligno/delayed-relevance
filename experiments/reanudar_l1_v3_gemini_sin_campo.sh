#!/usr/bin/env bash
# Reanuda la condicion "sin campo" de Gemini en L1 v3, que murio por un
# RemoteDisconnected no reintentado. Espera a que quede un hueco de Vertex (maximo dos
# procesos de Gemini) y reanuda desde su checkpoint.
set -u
cd "$(dirname "$0")/.."
export PYTHONPATH=src:.
while [ "$(pgrep -f '[g]emini-3-flash-preview --provider vertex' | wc -l | tr -d ' ')" -ge 2 ]; do sleep 60; done
echo "=== reanudo gemini sin campo $(date) ===" >> logs/l1_v3.log
.venv/bin/python experiments/probe_a.py --horizon 50 --seed-list 0 3 6 --estricto --repeats 8 \
  --ks 40 --only react skillstate --max-tokens 8192 --model gemini-3-flash-preview \
  --provider vertex --thinking-budget 0 >> logs/l1_v3.log 2>&1
echo "gemini sin campo reanudada terminada: $(date)" >> logs/l1_v3.log
