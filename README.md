# delayed-relevance

Replicacion de [SKILL.state](https://arxiv.org/abs/2608.26263) y medicion de la frontera
que el paper declara y no mide: que pasa cuando una observacion se vuelve relevante `k`
pasos despues de haber sido observada.

Diseno completo: ver el spec enlazado desde el articulo.

- [`docs/resultados-bloque1.md`](docs/resultados-bloque1.md) — replica, coste efectivo con
  cache, sonda de relevancia diferida, y que afirmacion sobrevive a que nivel de ruido.
- [`docs/metodo-medir-el-instrumento.md`](docs/metodo-medir-el-instrumento.md) — notas de
  metodo: medir el ruido del instrumento antes que el fenomeno, y los ocho artefactos que
  costo aprenderlo.

## Uso

    pip install -e ".[dev]"
    export ANTHROPIC_API_KEY=...   # o ANTHROPIC_FOUNDRY_API_KEY + _RESOURCE, o un .env
    pytest
    python experiments/replicate_table1.py --horizon 10 --seeds 1 --model claude-haiku-4-5

Antes de gastar en una rejilla, comprobar la densidad de contexto (no llama a la API):

    python experiments/measure_density.py --horizons 10 25 50

## Corridas largas en segundo plano

**Lanzarlas siempre con `exec`:**

    cd /ruta/al/repo && exec python experiments/replicate_table1.py --horizon 50 --seeds 5

Sin `exec`, el shell lanza `python` como hijo y se queda de intermediario. Al parar la
tarea se mata el shell, pero **en Windows matar al padre no mata al hijo**: el proceso
queda huerfano y sigue gastando llamadas a la API sin que nadie lo vea. Con `exec`, el
shell se reemplaza por el proceso de Python, asi que la tarea *es* el experimento y
pararla lo para de verdad.

Sintoma de que ha pasado: una corrida "detenida" cuyo fichero de resultados sigue
creciendo, o un `python.exe` cuyo padre ya no existe.

Buscar huerfanos y matarlos:

    # PowerShell
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
      Where-Object { $_.CommandLine -match 'replicate_table1' } |
      ForEach-Object { "$($_.ProcessId): $($_.CommandLine)" }

Perder una corrida no cuesta lo ya pagado: cada episodio se guarda en
`results/partial_*.json` en cuanto termina y al relanzar se saltan los completados.
