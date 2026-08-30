from dr.metrics import score, aggregate, paired_ttest
from dr.types import StepResult


def _result(actionable: bool, correct: bool) -> StepResult:
    return StepResult(step=0, actionable=actionable, correct=correct, prompt_tokens=10, output_tokens=2)


def test_score_counts_only_actionable_events():
    results = [_result(True, True), _result(True, False), _result(False, False)]
    assert score(results) == 0.5


def test_score_is_one_when_all_actionable_are_correct():
    assert score([_result(True, True), _result(False, False)]) == 1.0


def test_score_is_zero_when_there_are_no_actionable_events():
    assert score([_result(False, False)]) == 0.0


def test_aggregate_returns_mean_and_sd():
    summary = aggregate([1.0, 0.8, 0.9])
    assert round(summary.mean, 3) == 0.9
    assert summary.sd > 0


def test_paired_ttest_detects_a_real_difference():
    p = paired_ttest([0.9, 0.91, 0.92, 0.89, 0.90], [0.5, 0.51, 0.49, 0.52, 0.50])
    assert p < 0.01
