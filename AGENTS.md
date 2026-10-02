# AGENTS.md — delayed-relevance

Replicacion de *SKILL.state* (Tabla 1, entorno Warehouse reimplementado) y medicion de
relevancia diferida / invalidacion retroactiva en runtimes de agente. Repo personal y
**publico** en GitHub: nada de claves, nombres de recursos internos ni datos de terceros
en ficheros versionados. Contexto general y alcance: `README.md`.

## Estructura

- `src/dr/` — paquete (`pip install -e`, `packages.find where=src`).
  - `envs/` — entornos: `warehouse.py` (el del paper), `repo.py`, `longspec.py`, `base.py`.
  - `runtimes/` — los cuatro comparados: `react.py`, `memory.py`, `stateful.py`, `skillstate.py`.
  - `llm.py` — clientes Anthropic (API directa o Azure Foundry) y Gemini (AI Studio o
    Vertex); `build_client(model, provider)` enruta `gemini-*` a Gemini y el resto a Anthropic.
  - `runner.py`, `metrics.py`, `types.py`, `config.py` (carga `.env`), `keepawake.py`
    (evita la suspension en Windows durante rejillas largas).
- `experiments/` — un corredor por pregunta (`replicate_table1.py`, `probe_a.py`,
  `diagnose_probeC.py`, `adjudicar.py`, ...), informes (`report_*.py`, `resumen_l1.py`,
  `tabla_repeticiones.py`) y scripts de tanda `lanzar_*.sh`.
- `results/` — JSON/JSONL de resultados, **versionados a proposito** (auditabilidad del
  articulo). `results/aborted-*` son corridas descartadas que se conservan como evidencia;
  `results_mt1200/` es la remedicion con tope de salida 1.200 (`docs/resultados-bloque1.md`).
- `docs/` — en espanol: `resultados-bloque1.md`, `metodo-medir-el-instrumento.md`,
  `resultados-con-repeticiones.md`, `fidelidad-entorno.md`, `spec-paper.md`, `paper-draft.md`,
  `wif-actions.md`.
- `logs/` — salida de las tandas `lanzar_*.sh` (parte esta versionada).
- `.github/workflows/experimento.yml` — rejillas en Actions, solo `workflow_dispatch`.

## Comandos

    pip install -e ".[dev]"          # extra opcional: .[foundry] (azure-identity)
    pytest                           # testpaths=tests, -q
    python experiments/measure_density.py --horizons 10 25 50     # sin llamadas a la API
    python experiments/replicate_table1.py --horizon 10 --seeds 1 --model claude-haiku-4-5
    python experiments/adjudicar.py --horizon 50 --runtime react --seed 0 --model ... --provider ...

Comprobar la densidad de contexto antes de gastar en una rejilla.

## Credenciales y proveedores

- Claves en `.env` (gitignored) o en el entorno; `src/dr/config.py` las carga sin pisar
  variables ya definidas. Nunca pasar claves por linea de comandos.
- `--provider auto`: Foundry si hay cualquier `ANTHROPIC_FOUNDRY_*`, si no API directa
  (`ANTHROPIC_API_KEY`). Gemini: `GEMINI_API_KEY` (AI Studio) o `vertex`
  (`gcloud auth login`; proyecto en `GEMINI_VERTEX_PROJECT`/`GOOGLE_CLOUD_PROJECT`).
- Foundry sin clave usa token de `az` y lo renueva antes de caducar; Vertex espera y
  reintenta si caduca la sesion de gcloud.
- Workflow de Actions: la ruta operativa es `provider: auto` con `GEMINI_API_KEY`.
  `vertex` (WIF) no esta dado de alta; ver `docs/wif-actions.md`. No anadir disparadores
  distintos de `workflow_dispatch`: el repo es publico y expondria los secretos a forks.

## Corridas largas

- Lanzarlas con `exec` (`cd <repo> && exec python experiments/...`): sin `exec`, en Windows
  matar la tarea deja el `python` hijo huerfano gastando API. Detalle en `README.md`.
- Todo corredor es reanudable: checkpoint por episodio en `results/partial_*.json`
  (`adjudicar.py` salta trazas completas). Relanzar, no borrar parciales.
- Los `lanzar_*.sh` usan `.venv/bin/python` y varios paralelizan con `xargs -P` (fijo en cada
  script; `lanzar_r2.sh` lo lee de `$PARALELO`, por defecto 5).

## Convenciones y gotchas

- Codigo, comentarios, docs y mensajes de commit en espanol (README mixto ingles/espanol).
- Comparar modelos solo con condiciones identicas (mismo `--max-tokens`, `--apendice-b`,
  `--sin-telemetria`): topes de salida distintos ya produjeron una conclusion falsa.
- Medir el ruido del instrumento antes que el fenomeno (`docs/metodo-medir-el-instrumento.md`):
  un resultado limpio puede ser un artefacto (truncado, forma del JSON, cache contada dos veces).
- Nuevas funciones: test en `tests/test_*.py` siguiendo el patron existente.
