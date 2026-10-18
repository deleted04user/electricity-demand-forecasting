"""Reject ambiguous metric shapes instead of silently scoring a different task."""

import numpy as np
import pytest
from backend.modeling import calculate_metrics


@pytest.mark.parametrize("actual,predicted", [(1.0, 1.0), ([[1.0], [2.0]], [[1.0], [3.0]])])
def test_metrics_require_one_dimensional_observation_sequences(actual, predicted):
    with pytest.raises(ValueError, match="one-dimensional"):
        calculate_metrics(actual, predicted)


def test_constant_targets_have_undefined_r_squared_but_valid_error_metrics():
    metrics = calculate_metrics([10.0, 10.0], [9.0, 11.0])
    assert np.isnan(metrics["r2"])
    assert metrics["mae"] == 1.0
    assert metrics["wape"] == 10.0
