import { useEffect, useState } from "react";
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from "recharts";
import { api } from "../api";
import Metric from "../components/Metric";

export default function ModelPerformance() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.modelPerformance().then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="error">Failed to load: {error} <button onClick={() => window.location.reload()}>Retry backend connection</button></div>;
  if (!data) return <div className="loading">Loading model performance...</div>;

  const histData = data.error_histogram.map((count, i) => ({
    bin: data.error_bin_edges[i].toFixed(0),
    count,
  }));

  return (
    <div>
      <div className="warning-banner">
        Metrics below are computed on <strong>{data.test_period.start.slice(0, 10)} to {data.test_period.end.slice(0, 10)}</strong> —
        a held-out test set the model never saw during training or early stopping.
      </div>

      <p>Training: through 2022. Early stopping: 2023. Final held-out evaluation: 2024.
        These are historical one-step metrics using observed previous demand and weather, not recursive future accuracy.</p>
      {data.baselines && <div className="card"><div className="section-title">Naive baseline comparison (same test rows)</div>
        <table><thead><tr><th>Model</th><th>MAE (MW)</th><th>RMSE (MW)</th><th>R²</th><th>WAPE (%)</th></tr></thead>
          <tbody>{Object.entries(data.baselines).map(([name, metrics]) =>
            <tr key={name}><td>{name}</td><td>{metrics.mae}</td><td>{metrics.rmse}</td><td>{metrics.r2}</td><td>{metrics.wape}</td></tr>)}</tbody>
        </table></div>}
      <div className="grid grid-4">
        <Metric label="MAE" value={`${data.metrics.mae} MW`} sub="Mean Absolute Error" />
        <Metric label="RMSE" value={`${data.metrics.rmse} MW`} sub="Root Mean Squared Error" />
        <Metric label="R² Score" value={data.metrics.r2} sub={`Explains ${(data.metrics.r2 * 100).toFixed(1)}% of variance`} />
        <Metric label="WAPE" value={`${data.metrics.wape}%`} sub="Weighted Absolute % Error" />
      </div>
      {data.horizon_metrics && <div className="card"><div className="section-title">Horizon-specific evaluation</div>
        <p>One-step uses observed lag/weather inputs. Multi-step values are sampled recursive historical-proxy estimates; they are not interchangeable.</p>
        <table><thead><tr><th>Mode / horizon</th><th>MAE</th><th>RMSE</th><th>WAPE</th></tr></thead><tbody>
          <tr><td>Observed-lag one-step</td><td>{data.horizon_metrics.one_step_observed_lag.mae}</td><td>{data.horizon_metrics.one_step_observed_lag.rmse}</td><td>{data.horizon_metrics.one_step_observed_lag.wape}%</td></tr>
          {Object.entries(data.horizon_metrics.recursive_multi_step).map(([h, value]) => <tr key={h}><td>Recursive {h}h</td><td>{value.metrics.mae}</td><td>{value.metrics.rmse}</td><td>{value.metrics.wape}%</td></tr>)}
        </tbody></table></div>}

      <div className="card">
        <div className="section-title">Actual vs Predicted Demand (daily average)</div>
        <ResponsiveContainer width="100%" height={350}>
          <LineChart data={data.actual_vs_predicted}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={60} />
            <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="actual" stroke="#1565c0" dot={false} name="Actual" />
            <Line type="monotone" dataKey="predicted" stroke="#e53935" dot={false} strokeDasharray="5 3" name="Predicted" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="section-title">Error Distribution</div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={histData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="bin" tick={{ fontSize: 10 }} interval={4} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="count" fill="#1565c0" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div className="section-title">Feature Importance (top 15)</div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={data.feature_importance} layout="vertical" margin={{ left: 40 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis type="category" dataKey="feature" tick={{ fontSize: 10 }} width={140} />
              <Tooltip />
              <Bar dataKey="importance" fill="#1565c0" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
