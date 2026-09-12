import { useEffect, useState } from "react";
import { api } from "../api";
import Metric from "../components/Metric";

export default function Forecast() {
  const [horizon, setHorizon] = useState(24);
  const [future, setFuture] = useState(null);
  const [busy, setBusy] = useState(false);
  const [futureError, setFutureError] = useState(null);
  const [meta, setMeta] = useState(null);
  const [date, setDate] = useState("");
  const [hour, setHour] = useState(12);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.meta().then((m) => {
      setMeta(m);
      setDate(m.max_date); // default to the last available day
    }).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!date) return;
    setError(null);
    api.forecast(date, hour).then(setResult).catch((e) => {
      setError(e.message);
      setResult(null);
    });
  }, [date, hour]);

  return (
    <div>
      <div className="warning-banner">
        <strong>Local synthetic-data demonstration.</strong> Historical comparisons use observed weather and demand history.
        Future predictions recursively use predicted demand and a historical weather proxy.
      </div>

      <div className="card">
        <div className="section-title">Future forecast</div>
        <p>Starts at {meta?.future_start || "the next hour after historical data"}. Weather uses a configured local forecast when available; otherwise it uses historical month/hour averages, not a real weather forecast.</p>
        {meta?.data_quality && <p className={meta.data_quality.status === "ready" ? "status-ok" : "warning-banner"}>Data quality: {meta.data_quality.status.replaceAll("_", " ")} — {meta.data_quality.hourly_gaps} hourly gaps, {meta.data_quality.duplicates} duplicates, missing demand/weather: {meta.data_quality.missing.demand}/{meta.data_quality.missing.temperature + meta.data_quality.missing.humidity}.</p>}
        <label>Horizon (hours): <input type="number" min="1" max="168" value={horizon}
          onChange={(e) => setHorizon(Number(e.target.value))} /></label>{" "}
        <button disabled={!meta?.future_start || busy || !Number.isInteger(horizon) || horizon < 1 || horizon > 168}
          onClick={async () => {
            setBusy(true); setFutureError(null); setFuture(null);
            try { setFuture(await api.futureForecast(meta.future_start, horizon)); }
            catch (e) { setFutureError(e.message); }
            finally { setBusy(false); }
          }}>{busy ? "Forecasting…" : "Generate future forecast"}</button>
        {futureError && <div className="error">{futureError}</div>}
        {future && <><p><strong>{(future.forecast_mode || "experimental recursive").replaceAll("_", " ")}</strong>: {future.horizon_note || "Historical proxy; not real weather"}</p><p>{future.weather_description}</p>
          <div style={{ maxHeight: 350, overflow: "auto" }}><table>
            <thead><tr><th>Timestamp</th><th>Predicted demand (MW)</th><th>Estimated 90% interval (MW)</th></tr></thead>
            <tbody>{future.forecast.map((row) => <tr key={row.timestamp}><td>{row.timestamp}</td><td>{row.predicted}</td><td>{row.prediction_interval ? `${row.prediction_interval.lower} – ${row.prediction_interval.upper}` : "Interval unavailable"}</td></tr>)}</tbody>
          </table></div></>}
      </div>
      <h2>Historical actual vs predicted comparison</h2>
      {meta && (
        <div className="controls card">
          <label>
            Date:{" "}
            <input
              type="date"
              value={date}
              min={meta.min_date}
              max={meta.max_date}
              onChange={(e) => setDate(e.target.value)}
            />
          </label>
          <label style={{ flex: 1 }}>
            Hour: {hour}:00
            <input
              type="range" min="0" max="23" value={hour}
              onChange={(e) => setHour(Number(e.target.value))}
              style={{ width: "100%" }}
            />
          </label>
        </div>
      )}

      {error && <div className="error">{error} <button onClick={() => window.location.reload()}>Retry backend connection</button></div>}

      {result && (
        <>
          <div className="grid grid-2">
            <Metric label="Actual Demand" value={`${result.actual} MW`} sub="From historical data" />
            <Metric label="Predicted Demand" value={`${result.predicted} MW`} sub={result.prediction_interval ? `Estimated 90% interval: ${result.prediction_interval.lower}–${result.prediction_interval.upper} MW (not guaranteed)` : `Error: ${result.error} MW`} />
          </div>

          <div className="grid grid-2">
            <div className="card">
              <div className="section-title">Context</div>
              <table>
                <tbody>
                  <tr><td>Day</td><td>{result.context.day_of_week}</td></tr>
                  <tr><td>Temperature</td><td>{result.context.temperature} °C</td></tr>
                  <tr><td>Humidity</td><td>{result.context.humidity} %</td></tr>
                  <tr><td>Day Type</td><td>{result.context.is_weekend ? "Weekend" : "Weekday"}</td></tr>
                  <tr><td>Holiday</td><td>{result.context.is_holiday ? "Yes" : "Regular day"}</td></tr>
                </tbody>
              </table>
            </div>

            <div className="card">
              <div className="section-title">Input Features</div>
              <table>
                <tbody>
                  {Object.entries(result.input_features).map(([k, v]) => (
                    <tr key={k}><td>{k}</td><td>{typeof v === "number" ? v.toFixed(2) : v}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
