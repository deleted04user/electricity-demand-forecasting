import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent, cleanup, act } from "@testing-library/react";
import mockPayloads from "../mock_payloads.json";
import Overview from "./pages/Overview";
import DemandAnalysis from "./pages/DemandAnalysis";
import ModelPerformance from "./pages/ModelPerformance";
import Forecast from "./pages/Forecast";
import App from "./App";

afterEach(() => { vi.useRealTimers(); cleanup(); });

function mockFetchFor(pathToPayload) {
  global.fetch = vi.fn((url) => {
    const path = new URL(url).pathname;
    const payload = pathToPayload[path];
    if (!payload) return Promise.resolve({ ok: false, status: 404, json: async () => ({ detail: "not mocked" }) });
    return Promise.resolve({ ok: true, json: async () => payload });
  });
}

describe("dashboard pages render against real backend payloads", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("Overview renders without crashing and shows real stats", async () => {
    mockFetchFor({ "/api/overview": mockPayloads.overview });
    render(<Overview />);
    await waitFor(() => expect(screen.getByText(/Total Observations/i)).toBeTruthy());
    expect(screen.getByText(mockPayloads.overview.total_observations.toLocaleString())).toBeTruthy();
  });

  it("DemandAnalysis renders without crashing", async () => {
    mockFetchFor({ "/api/demand-analysis": mockPayloads["demand-analysis"] });
    render(<DemandAnalysis />);
    await waitFor(() => expect(screen.getByText(/Demand by Hour of Day/i)).toBeTruthy());
  });

  it("ModelPerformance renders real metrics", async () => {
    mockFetchFor({ "/api/model-performance": mockPayloads["model-performance"] });
    render(<ModelPerformance />);
    await waitFor(() => expect(screen.getByText(/MAE/i)).toBeTruthy());
    expect(screen.getByText(`${mockPayloads["model-performance"].metrics.mae} MW`)).toBeTruthy();
    expect(screen.getByText(`${mockPayloads["model-performance"].metrics.wape}%`)).toBeTruthy();
    expect(screen.getByText(`Explains ${(mockPayloads["model-performance"].metrics.r2 * 100).toFixed(1)}% of variance`)).toBeTruthy();
  });

  it("Forecast renders and fetches a prediction", async () => {
    mockFetchFor({ "/api/meta": mockPayloads.meta, "/api/forecast": mockPayloads.forecast });
    render(<Forecast />);
    await waitFor(() => expect(screen.getByText(/Actual Demand/i)).toBeTruthy());
    await waitFor(() => expect(screen.getByText(`${mockPayloads.forecast.actual} MW`)).toBeTruthy());
  });

  it("App shell renders with tab navigation", async () => {
    mockFetchFor({ "/api/overview": mockPayloads.overview });
    render(<App />);
    expect(screen.getByText(/Electricity Demand Forecasting/i)).toBeTruthy();
    expect(screen.getByText("Model Performance")).toBeTruthy();
  });
});


it("generates a future forecast with the selected horizon", async () => {
  mockFetchFor({
    "/api/meta": { ...mockPayloads.meta, future_start: "2025-01-01 00:00:00" },
    "/api/forecast": mockPayloads.forecast,
    "/api/forecast/future": { weather_description: "Historical proxy; not real weather", forecast: [{ timestamp: "2025-01-01 00:00:00", predicted: 3000 }] },
  });
  render(<Forecast />);
  const button = await screen.findByRole("button", { name: "Generate future forecast" });
  await waitFor(() => expect(button.disabled).toBe(false));
  fireEvent.change(screen.getByLabelText("Horizon (hours):"), { target: { value: "2" } });
  fireEvent.click(button);
  expect(await screen.findByText("Historical proxy; not real weather")).toBeTruthy();
  const call = global.fetch.mock.calls.find(([url]) => String(url).endsWith("/api/forecast/future"));
  expect(JSON.parse(call[1].body)).toEqual({ start: "2025-01-01 00:00:00", horizon: 2 });
});

it("shows baseline comparison", async () => {
  mockFetchFor({ "/api/model-performance": { ...mockPayloads["model-performance"], baselines: { "24-hour naive": { mae: 178.25, rmse: 224.53, r2: .786, wape: 6.09 } } } });
  render(<ModelPerformance />);
  expect(await screen.findByText("24-hour naive")).toBeTruthy();
});

it("shows unavailable metrics without inventing zero scores and preserves scored-row counts", async () => {
  const unavailable = { mae: null, rmse: null, r2: null, wape: null, bias: null };
  const zeroErrors = { mae: 0, rmse: 0, r2: 0, wape: 0, bias: 0 };
  mockFetchFor({
    "/api/model-performance": {
      ...mockPayloads["model-performance"],
      metrics: unavailable,
      baselines: { "24-hour naive": unavailable },
      horizon_metrics: {
        one_step_observed_lag: unavailable,
        recursive_multi_step: {
          "1": { metrics: zeroErrors, origins: 2, scored_rows: 2 },
          "24": { metrics: unavailable, origins: 2, scored_rows: 0 },
        },
      },
    },
  });
  const { container } = render(<ModelPerformance />);
  await screen.findByText("Variance explanation unavailable");
  expect([...container.querySelectorAll(".metric-value")].map((node) => node.textContent))
    .toEqual(["Unavailable", "Unavailable", "Unavailable", "Unavailable"]);
  const cells = (name) => [...screen.getByRole("row", { name }).querySelectorAll("td")]
    .map((node) => node.textContent);
  expect(cells(/24-hour naive/)).toEqual(["24-hour naive", "Unavailable", "Unavailable", "Unavailable", "Unavailable"]);
  expect(cells(/Observed-lag one-step/)).toEqual(["Observed-lag one-step", "Unavailable", "Unavailable", "Unavailable", "—"]);
  expect(cells(/Recursive 24h/)).toEqual(["Recursive 24h", "Unavailable", "Unavailable", "Unavailable", "0"]);
  expect(cells(/Recursive 1h/)).toEqual(["Recursive 1h", "0", "0", "0%", "2"]);
  expect(container.textContent).not.toMatch(/null|undefined|NaN|Explains 0\.0% of variance/);
});

it("shows a future API error", async () => {
  mockFetchFor({ "/api/meta": { ...mockPayloads.meta, future_start: "2025-01-01 00:00:00" }, "/api/forecast": mockPayloads.forecast });
  render(<Forecast />);
  const button = await screen.findByRole("button", { name: "Generate future forecast" });
  await waitFor(() => expect(button.disabled).toBe(false));
  fireEvent.click(button);
  expect(await screen.findByText("not mocked")).toBeTruthy();
});

it("re-enables forecasting with a useful error when a backend request stalls", async () => {
  global.fetch = vi.fn((url, options) => {
    const path = new URL(url).pathname;
    if (path === "/api/forecast/future") {
      return new Promise((_resolve, reject) => {
        options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
      });
    }
    const payload = path === "/api/meta"
      ? { ...mockPayloads.meta, future_start: "2025-01-01 00:00:00" }
      : mockPayloads.forecast;
    return Promise.resolve({ ok: true, json: async () => payload });
  });
  render(<Forecast />);
  await screen.findByText("Actual Demand");
  const button = screen.getByRole("button", { name: "Generate future forecast" });
  vi.useFakeTimers();
  fireEvent.click(button);
  expect(button.disabled).toBe(true);
  await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
  expect(screen.getByText("Backend request timed out after 30 seconds. Please retry.")).toBeTruthy();
  expect(button.disabled).toBe(false);
  expect(button.textContent).toBe("Generate future forecast");
});

it("keeps the latest selected hour when historical requests finish out of order", async () => {
  const pending = new Map();
  global.fetch = vi.fn((url) => {
    const request = new URL(url);
    if (request.pathname === "/api/meta") {
      return Promise.resolve({ ok: true, json: async () => mockPayloads.meta });
    }
    return new Promise((resolve) => pending.set(request.searchParams.get("hour"), resolve));
  });
  render(<Forecast />);
  await waitFor(() => expect(pending.has("12")).toBe(true));
  fireEvent.change(screen.getByRole("slider"), { target: { value: "13" } });
  await waitFor(() => expect(pending.has("13")).toBe(true));
  expect(screen.getByRole("status").textContent).toContain("Loading historical forecast");

  await act(async () => {
    pending.get("13")({ ok: true, json: async () => ({ ...mockPayloads.forecast, actual: 1234 }) });
  });
  expect(await screen.findByText("1234 MW")).toBeTruthy();
  await act(async () => {
    pending.get("12")({ ok: true, json: async () => ({ ...mockPayloads.forecast, actual: 9999 }) });
  });
  expect(screen.getByText("1234 MW")).toBeTruthy();
  expect(screen.queryByText("9999 MW")).toBeNull();
});
