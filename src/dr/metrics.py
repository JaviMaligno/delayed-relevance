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
