import math
import unittest

import numpy as np
import pandas as pd

from backend.features import DEMAND_LAGS, ROLLING_WINDOWS, add_engineered_features
from backend.modeling import (
    CANDIDATES,
    ROLLING_FOLDS,
    calculate_metrics,
    chronological_splits,
    rolling_origin_splits,
)


class CausalFeatureTests(unittest.TestCase):
    def setUp(self):
        self.index = pd.date_range("2022-01-01", periods=400, freq="h")
        self.frame = pd.DataFrame(
            {
                "Demand": np.arange(400, dtype=float),
                "Temperature": np.arange(400, dtype=float) + 10,
                "Humidity": 50.0,
            },
            index=self.index,
        )

    def test_lags_and_rolls_use_strictly_past_demand(self):
        engineered = add_engineered_features(self.frame, holiday_dates=set())
        row = engineered.iloc[350]
        for lag in DEMAND_LAGS:
            self.assertEqual(row[f"demand_lag_{lag}h"], self.frame["Demand"].iloc[350 - lag])
        for window in ROLLING_WINDOWS:
            expected = self.frame["Demand"].iloc[350 - window:350]
            self.assertAlmostEqual(row[f"demand_rolling_mean_{window}h"], expected.mean())
            self.assertAlmostEqual(row[f"demand_rolling_std_{window}h"], expected.std())

        changed = self.frame.copy()
        changed.loc[self.index[350]:, "Demand"] = 999999.0
        changed_features = add_engineered_features(changed, holiday_dates=set())
        causal_columns = [
            *(f"demand_lag_{lag}h" for lag in DEMAND_LAGS),
            *(f"demand_rolling_{stat}_{window}h" for window in ROLLING_WINDOWS for stat in ("mean", "std")),
        ]
        pd.testing.assert_series_equal(
            engineered.loc[self.index[350], causal_columns],
            changed_features.loc[self.index[350], causal_columns],
        )

    def test_weather_fill_is_forward_only(self):
        frame = self.frame.copy()
        frame.loc[self.index[:2], "Temperature"] = np.nan
        frame.loc[self.index[10], "Temperature"] = np.nan
        engineered = add_engineered_features(frame, holiday_dates=set())
        self.assertTrue(pd.isna(engineered.loc[self.index[0], "Temperature"]))
        self.assertTrue(pd.isna(engineered.loc[self.index[1], "Temperature"]))
        self.assertEqual(engineered.loc[self.index[10], "Temperature"], frame.loc[self.index[9], "Temperature"])


class EvaluationTests(unittest.TestCase):
    def test_chronological_splits_and_folds_do_not_overlap(self):
        index = pd.date_range("2020-01-01", "2024-12-31 23:00:00", freq="h")
        frame = pd.DataFrame({"value": 1}, index=index)
        splits = chronological_splits(frame)
        self.assertLess(splits["train"].index.max(), splits["tuning"].index.min())
        self.assertLess(splits["tuning"].index.max(), splits["test"].index.min())
        self.assertEqual(splits["test"].index.min(), pd.Timestamp("2024-01-01"))
        folds = rolling_origin_splits(frame.loc[:"2023-12-31 23:00:00"])
        self.assertEqual(len(folds), 3)
        for _, train, validation in folds:
            self.assertLess(train.index.max(), validation.index.min())
            self.assertLess(validation.index.max(), pd.Timestamp("2024-01-01"))
        self.assertLessEqual(len(CANDIDATES), 12)
        self.assertLessEqual(len(ROLLING_FOLDS), 3)

    def test_metrics_fixed_example(self):
        metrics = calculate_metrics([100.0, 200.0], [90.0, 220.0])
        self.assertEqual(metrics["mae"], 15.0)
        self.assertAlmostEqual(metrics["rmse"], math.sqrt(250.0))
        self.assertAlmostEqual(metrics["r2"], 0.9)
        self.assertAlmostEqual(metrics["wape"], 10.0)
        self.assertAlmostEqual(metrics["bias"], 5.0)


if __name__ == "__main__":
    unittest.main()
