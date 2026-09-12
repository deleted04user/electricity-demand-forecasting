import { lazy, Suspense, useState } from "react";
const Overview = lazy(() => import("./pages/Overview"));
const DemandAnalysis = lazy(() => import("./pages/DemandAnalysis"));
const ModelPerformance = lazy(() => import("./pages/ModelPerformance"));
const Forecast = lazy(() => import("./pages/Forecast"));

const TABS = [
  { key: "overview", label: "Overview", Component: Overview },
  { key: "analysis", label: "Demand Analysis", Component: DemandAnalysis },
  { key: "performance", label: "Model Performance", Component: ModelPerformance },
  { key: "forecast", label: "Forecast", Component: Forecast },
];

export default function App() {
  const [active, setActive] = useState("overview");
  const ActiveComponent = TABS.find((t) => t.key === active).Component;

  return (
    <div className="app">
      <div className="header">
        <h1>⚡ Electricity Demand Forecasting</h1>
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`tab ${active === t.key ? "active" : ""}`}
            onClick={() => setActive(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <Suspense fallback={<div className="loading">Loading page…</div>}><ActiveComponent /></Suspense>
    </div>
  );
}
