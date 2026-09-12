const BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

async function get(path, params = {}) {
  const url = new URL(BASE_URL + path);
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  overview: () => get("/api/overview"),
  demandAnalysis: () => get("/api/demand-analysis"),
  modelPerformance: () => get("/api/model-performance"),
  forecast: (date, hour) => get("/api/forecast", { date, hour }),
  futureForecast: async (start, horizon) => {
    const res = await fetch(BASE_URL + "/api/forecast/future", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start, horizon }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Invalid forecast request");
    return body;
  },
  meta: () => get("/api/meta"),
};
