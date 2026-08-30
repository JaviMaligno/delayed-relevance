# delayed-relevance

Replicacion de [SKILL.state](https://arxiv.org/abs/2608.26263) y medicion de la frontera
que el paper declara y no mide: que pasa cuando una observacion se vuelve relevante `k`
pasos despues de haber sido observada.

Diseno completo: ver el spec enlazado desde el articulo.

## Uso

    pip install -e ".[dev]"
    export ANTHROPIC_API_KEY=...
    pytest
    python experiments/replicate_table1.py --horizon 10 --seeds 1 --model claude-haiku-4-5
