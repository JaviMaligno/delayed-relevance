# delayed-relevance

Replication of [*SKILL.state: Scalable Long-Horizon Agent Skills*](https://arxiv.org/abs/2608.26263)
(Badhe, Tiwari and Chung), plus the boundary the paper declares and does not measure: what
happens when an observation becomes relevant `k` steps after it was read.

Write-up: **[When the Fact Stops Being True](https://www.javieraguilar.ai/en/blog/when-the-fact-stops-being-true)**
· [en espanol](https://www.javieraguilar.ai/es/blog/when-the-fact-stops-being-true).
The code is English-commented where it matters; the two design docs are in Spanish.

## Scope

|  | this repo | the paper |
|---|---|---|
| models | Claude Haiku 4.5, Claude Sonnet 5 | Gemini-3-Flash, Gemma-4-31B-it, Qwen-3-8B-it |
| environment | Warehouse, reimplemented from their §4.1 | Warehouse, Software Repository |
| horizons | T ∈ {10, 25, 50, 100, 200} | the same |
| context density | 1.2–1.4x theirs, by average prompt in characters | — |

SkillExecBench has no public code, so the environment is a reimplementation matched on
**context density**, not on literal content. Every number in the article comes from the JSON
under [`results/`](results/), which is committed on purpose: the argument of the write-up is
that this class of experiment fails by producing clean results, so the data has to be
auditable. The three `results/aborted-*` directories are runs discarded because of the
artefacts documented below — they are kept as the evidence for them.

## What is here

- [`docs/resultados-bloque1.md`](docs/resultados-bloque1.md) — full results: the Table 1
  replication across their whole horizon range, effective cost with prompt caching measured
  at two procedure lengths, the delayed-relevance and retroactive-invalidation probes, and
  which claim survives which level of noise.
- [`docs/metodo-medir-el-instrumento.md`](docs/metodo-medir-el-instrumento.md) — method
  notes: measure the instrument's noise before the phenomenon, and the nine artefacts it
  took to learn that. Two of the nine were caught auditing results that were already
  written up.
- [`experiments/`](experiments/) — one runner per question, all with per-episode
  checkpointing so an interrupted grid resumes without re-paying.
- [`src/dr/runtimes/`](src/dr/runtimes/) — the four runtimes compared: ReAct, Memory,
  Stateful and SKILL.state.

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
