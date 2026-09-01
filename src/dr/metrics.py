from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from dr.types import StepResult


@dataclass(frozen=True)
class Summary:
    mean: float
    sd: float


def score(results: list[StepResult]) -> float:
    actionable = [result for result in results if result.actionable]
    if not actionable:
        return 0.0
    return sum(1 for result in actionable if result.correct) / len(actionable)


def aggregate(scores: list[float]) -> Summary:
    array = np.asarray(scores, dtype=float)
    return Summary(mean=float(array.mean()), sd=float(array.std(ddof=1)))


def paired_ttest(left: list[float], right: list[float]) -> float:
    _, p_value = stats.ttest_rel(left, right)
    return float(p_value)


# Multiplicadores de la tarifa de Anthropic sobre el precio de entrada.
PRECIO_CACHE_LECTURA = 0.10
PRECIO_CACHE_ESCRITURA = 1.25


def coste_efectivo(results: list[StepResult]) -> dict[str, float]:
    """Tokens de entrada equivalentes a precio completo, con y sin cache.

    El paper compara TOKENS; quien paga la factura compara DINERO. Un transcript
    append-only cachea casi entero y se cobra a 0.1x, mientras un bloque de estado
    que muta invalida la cache y se cobra completo. Medir solo tokens brutos
    sobreestima la ventaja del estado explicito.
    """
    # `input_tokens` de la API NO incluye los cacheados: los reporta aparte. La entrada
    # total es la suma de los tres. Restar el cache de `input_tokens` da coste negativo,
    # que es exactamente el error que produjo un "ahorro del 624%".
    sin_cachear = sum(r.prompt_tokens for r in results)
    leidos = sum(r.cache_read for r in results)
    escritos = sum(r.cache_write for r in results)
    brutos = sin_cachear + leidos + escritos
    efectivo = sin_cachear + leidos * PRECIO_CACHE_LECTURA + escritos * PRECIO_CACHE_ESCRITURA
    return {
        "tokens_brutos": brutos,
        "cache_lectura": leidos,
        "cache_escritura": escritos,
        "sin_cachear": sin_cachear,
        "entrada_efectiva": efectivo,
        "ahorro_por_cache": 1 - (efectivo / brutos) if brutos else 0.0,
    }
