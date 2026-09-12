import { useEffect, useState } from "react";
import {
  LineChart, Line, BarChart, Bar, ScatterChart, Scatter,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { api } from "../api";

const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

export default function DemandAnalysis() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.demandAnalysis().then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="error">Failed to load: {error}</div>;
  if (!data) return <div className="loading">Loading demand analysis...</div>;

  const monthly = data.monthly_avg.map((m) => ({ ...m, name: MONTH_NAMES[m.month - 1] }));
  const dayTypeData = [
    { name: "Weekday", demand: data.weekday_vs_weekend.weekday },
    { name: "Weekend", demand: data.weekday_vs_weekend.weekend },
  ];

  return (
    <div>
      <div className="grid grid-2">
        <div className="card">
          <div className="section-title">Demand by Hour of Day</div>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={data.hourly_avg}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
              <Tooltip />
              <Line type="monotone" dataKey="demand" stroke="#ef6c00" strokeWidth={2} dot />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div className="section-title">Demand by Month</div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={monthly}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
              <Tooltip />
              <Bar dataKey="demand" fill="#7cb342" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <div className="section-title">Weekday vs Weekend</div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={dayTypeData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} domain={["auto", "auto"]} />
              <Tooltip />
              <Bar dataKey="demand">
                <Cell fill="#1565c0" />
                <Cell fill="#ef6c00" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div className="section-title">Demand vs Temperature</div>
          <ResponsiveContainer width="100%" height={280}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="temperature" name="Temperature" unit="°C" tick={{ fontSize: 11 }} />
              <YAxis dataKey="demand" name="Demand" unit=" MW" tick={{ fontSize: 11 }} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} />
              <Scatter data={data.temp_vs_demand_sample} fill="#8e24aa" opacity={0.4} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <div className="section-title">Feature Correlations</div>
        <CorrelationHeatmap matrix={data.correlation_matrix} />
      </div>
    </div>
  );
}

function CorrelationHeatmap({ matrix }) {
  const { columns, values } = matrix;
  const colorFor = (v) => {
    // -1 (blue) .. 0 (white) .. 1 (red)
    const t = (v + 1) / 2;
    const r = Math.round(255 * t + 40 * (1 - t));
    const b = Math.round(255 * (1 - t) + 40 * t);
    return `rgb(${r}, 245, ${b})`;
  };
  return (
    <table>
      <thead>
        <tr>
          <th></th>
          {columns.map((c) => <th key={c} style={{ fontSize: 11 }}>{c}</th>)}
        </tr>
      </thead>
      <tbody>
        {values.map((row, i) => (
          <tr key={columns[i]}>
            <td style={{ fontSize: 11, fontWeight: 600 }}>{columns[i]}</td>
            {row.map((v, j) => (
              <td key={j} style={{ background: colorFor(v), textAlign: "center", fontSize: 11 }}>
                {v}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
