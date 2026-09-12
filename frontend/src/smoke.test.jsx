import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent, cleanup } from "@testing-library/react";
import mockPayloads from "../mock_payloads.json";
import Overview from "./pages/Overview";
import DemandAnalysis from "./pages/DemandAnalysis";
import ModelPerformance from "./pages/ModelPerformance";
import Forecast from "./pages/Forecast";
import App from "./App";

afterEach(() => cleanup());

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

it("shows a future API error", async () => {
  mockFetchFor({ "/api/meta": { ...mockPayloads.meta, future_start: "2025-01-01 00:00:00" }, "/api/forecast": mockPayloads.forecast });
  render(<Forecast />);
  const button = await screen.findByRole("button", { name: "Generate future forecast" });
  await waitFor(() => expect(button.disabled).toBe(false));
  fireEvent.click(button);
  expect(await screen.findByText("not mocked")).toBeTruthy();
});
