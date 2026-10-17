const BASE_URL = (import.meta.env.VITE_API_BASE_URL || window.location.origin).replace(/\/+$/, "");

async function readResponse(res) {
  const body = await res.json().catch(() => {
    if (res.ok) throw new Error("Backend returned an invalid JSON response");
    return {};
  });
  if (!res.ok) {
    // Validation errors can contain structured FastAPI details; never render an
    // object as a React child or expose an HTML proxy error to the dashboard.
    const detail = typeof body?.detail === "string" ? body.detail : null;
    throw new Error(detail || `Request failed: ${res.status}`);
  }
  return body;
}

async function get(path, params = {}) {
  const url = new URL(BASE_URL + path);
  Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const res = await fetch(url);
  return readResponse(res);
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
    return readResponse(res);
  },
  meta: () => get("/api/meta"),
};
