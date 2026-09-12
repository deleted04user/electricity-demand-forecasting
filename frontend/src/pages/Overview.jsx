import { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { api } from "../api";
import Metric from "../components/Metric";
import StatsTable from "../components/StatsTable";

export default function Overview() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.overview().then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="error">Failed to load: {error}. Is the backend running on :8000?</div>;
  if (!data) return <div className="loading">Loading overview...</div>;

  return (
    <div>
      <div className="warning-banner">
        <strong>IMPORTANT:</strong> This dashboard uses a SYNTHETIC (simulated) dataset representing typical
        residential electricity consumption patterns. Results should not be used for real-world decisions
        without validation on actual data.
      </div>

      <div className="grid grid-4">
        <Metric label="Total Observations" value={data.total_observations.toLocaleString()} sub="Hourly readings" />
        <Metric
          label="Date Range"
          value={data.date_range.start.slice(0, 10)}
          sub={`to ${data.date_range.end.slice(0, 10)}`}
        />
        <Metric
          label="Avg Demand"
          value={`${data.demand_stats.mean} MW`}
          sub={`± ${data.demand_stats.std} MW`}
        />
        <Metric
          label="Peak Demand"
          value={`${data.demand_stats.max} MW`}
          sub={`Min: ${data.demand_stats.min} MW`}
        />
      </div>

      <div className="card">
        <div className="section-title">Electricity Demand Over Time (daily average)</div>
        <ResponsiveContainer width="100%" height={350}>
          <LineChart data={data.demand_timeseries}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} minTickGap={60} />
            <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
            <Tooltip />
            <Line type="monotone" dataKey="demand" stroke="#1565c0" dot={false} strokeWidth={1.5} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-2">
        <StatsTable title="Demand Statistics" stats={data.demand_stats} unit="MW" />
        <StatsTable title="Temperature Statistics" stats={data.temperature_stats} unit="°C" />
      </div>
    </div>
  );
}
