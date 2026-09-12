import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.features import add_engineered_features

client = TestClient(main.app)


def test_health_overview_meta():
    assert client.get('/api/health').json()['model_ready']
    assert client.get('/api/overview').json()['total_observations'] > 0
    analysis = client.get('/api/demand-analysis')
    assert analysis.status_code == 200
    assert analysis.json()['temp_vs_demand_sample']
    meta = client.get('/api/meta').json()
    assert meta['future_start'] == '2025-01-01 00:00:00'
    assert 'data_quality' in meta and 'model_data_compatible' in meta['data_quality']


def test_historical():
    response = client.get('/api/forecast', params={'date': '2024-12-31', 'hour': 12})
    assert response.status_code == 200
    assert response.json()['prediction_interval']['not_a_guarantee'] is True
    for date, hour, code in [('bad', 12, 400), ('2024-01-01', 24, 422), ('2030-01-01', 0, 404), ('2020-01-01', 0, 400)]:
        assert client.get('/api/forecast', params={'date': date, 'hour': hour}).status_code == code


def test_future():
    payload = {'start': '2025-01-01T00:00:00', 'horizon': 25}
    response = client.post('/api/forecast/future', json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body['weather_source'] == 'historical_proxy'
    assert len(body['forecast']) == 25
    assert body['forecast'][-1]['timestamp'] == '2025-01-02 00:00:00'
    payload.update(horizon=2, temperature=[20, 21], humidity=[50, 55])
    assert client.post('/api/forecast/future', json=payload).json()['weather_source'] == 'supplied'


@pytest.mark.parametrize('change', [{'horizon': 0}, {'horizon': 169}, {'horizon': 1.5}, {'start': 'bad'}, {'start': '2026-01-01'}, {'start': '2025-01-01T00:00:00Z'}, {'temperature': [20]}, {'temperature': [20], 'humidity': [50]}, {'temperature': [20, 20], 'humidity': [101, 50]}])
def test_future_validation(change):
    response = client.post('/api/forecast/future', json={'start': '2025-01-01', 'horizon': 2, **change})
    assert 400 <= response.status_code < 500


def test_causal_features():
    frame = pd.DataFrame({'Demand': np.arange(220, dtype=float), 'Temperature': 20., 'Humidity': 50.}, index=pd.date_range('2024-01-01', periods=220, freq='h'))
    frame.loc[frame.index[0], 'Temperature'] = np.nan
    frame.loc[frame.index[190], ['Demand', 'Temperature']] = np.nan
    original = add_engineered_features(frame)
    changed = frame.copy()
    changed.loc[frame.index[200]:, :] = 9999
    engineered = add_engineered_features(changed)
    cols = ['Demand_lag_24hr', 'demand_lag_168hr', 'demand_rolling_mean_24hr', 'demand_rolling_std_24hr']
    pd.testing.assert_frame_equal(original.loc[:frame.index[200], cols], engineered.loc[:frame.index[200], cols])
    assert original.iloc[200]['Demand_lag_24hr'] == 176
    assert original.iloc[200]['demand_lag_168hr'] == 32
    assert original.iloc[200]['demand_rolling_mean_24hr'] == frame.Demand.ffill().iloc[176:200].mean()
    assert pd.isna(original.iloc[0].Temperature)
    assert original.iloc[190].Temperature == 20
    assert pd.isna(original.iloc[190].Demand)
    assert pd.isna(original.iloc[0]['Demand_lag_24hr'])


def test_recursive_predictions_feed_history(monkeypatch):
    class LagModel:
        def predict(self, features):
            column = 'demand_lag_24h' if 'demand_lag_24h' in features else 'Demand_lag_24hr'
            return features[column].to_numpy() + 1
    monkeypatch.setattr(main, 'MODEL', LagModel())
    start = pd.Timestamp('2025-01-01')
    rows = main.recursive_forecast(main.DATA, start, 25)
    assert rows[24]['predicted'] == pytest.approx(rows[0]['predicted'] + 1, abs=.01)


def test_baselines_and_split():
    body = client.get('/api/model-performance').json()
    assert set(body['baselines']) == {'24-hour naive', '168-hour naive'}
    assert body['early_stopping_period']['start'].startswith('2023')
    assert body['test_period']['start'].startswith('2024')
    assert set(body['horizon_metrics']['recursive_multi_step']) == {'1', '6', '24', '72', '168'}
    assert body['horizon_metrics']['one_step_observed_lag']['wape'] == body['metrics']['wape']
