import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import mockPayloads from "../mock_payloads.json";
import diagnostics from "../../models/diagnostics.json";
import DemandAnalysis from "./pages/DemandAnalysis";
import ModelPerformance from "./pages/ModelPerformance";

// jsdom has no layout. Give the real Recharts components a fixed viewport rather
// than replacing their charts, axes, or data transformations with mocks.
vi.mock("recharts", async (importOriginal) => {
  const original = await importOriginal();
  const { cloneElement } = await import("react");
  return {
    ...original,
    ResponsiveContainer: ({ children }) => cloneElement(children, { width: 960, height: 300 }),
  };
});

beforeEach(() => vi.stubGlobal("fetch", vi.fn()));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function respondWith(payload) {
  fetch.mockResolvedValue({ ok: true, json: async () => payload });
}

function card(title) {
  return screen.getByText(title, { exact: true }).closest(".card");
}

function rowCells(table, label) {
  const row = within(table).getByRole("row", { name: label });
  return within(row).getAllByRole("cell").map((cell) => cell.textContent);
}

describe("demand analysis values", () => {
  it("labels real seasonal charts and preserves correlation row/column alignment", async () => {
    const fixture = mockPayloads["demand-analysis"];
    const payload = {
      ...fixture,
      // Rendering thousands of scatter points adds no coverage to the seasonal
      // labels and correlation contract exercised here. Retain real samples.
      temp_vs_demand_sample: fixture.temp_vs_demand_sample.slice(0, 6),
    };
    respondWith(payload);
    render(<DemandAnalysis />);
    expect(screen.getByText("Loading demand analysis...")).toBeTruthy();
    await screen.findByText("Feature Correlations");

    expect(new URL(fetch.mock.calls[0][0]).pathname).toBe("/api/demand-analysis");
    const monthly = within(card("Demand by Month"));
    for (const month of ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]) {
      expect(monthly.getByText(month)).toBeTruthy();
    }
    const dayTypes = within(card("Weekday vs Weekend"));
    expect(dayTypes.getByText("Weekday")).toBeTruthy();
    expect(dayTypes.getByText("Weekend")).toBeTruthy();

    const table = within(card("Feature Correlations")).getByRole("table");
    const { columns, values } = payload.correlation_matrix;
    expect(within(table).getAllByRole("columnheader").slice(1).map((cell) => cell.textContent))
      .toEqual(columns);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(columns.length);
    for (const [index, row] of rows.entries()) {
      expect(within(row).getAllByRole("cell").map((cell) => cell.textContent))
        .toEqual([columns[index], ...values[index].map(String)]);
    }
    expect(screen.queryByText("Loading demand analysis...")).toBeNull();
  });
});

describe("model performance comparisons", () => {
  it("keeps real held-out scores, baselines and recursive horizon metrics in their own rows", async () => {
    const payload = diagnostics.performance;
    respondWith(payload);
    const { container } = render(<ModelPerformance />);
    expect(screen.getByText("Loading model performance...")).toBeTruthy();
    await screen.findByText("Horizon-specific evaluation");

    expect(new URL(fetch.mock.calls[0][0]).pathname).toBe("/api/model-performance");
    expect([...container.querySelectorAll(".metric-card")].map((metric) => [
      metric.querySelector(".metric-label").textContent,
      metric.querySelector(".metric-value").textContent,
    ])).toEqual([
      ["MAE", `${payload.metrics.mae} MW`],
      ["RMSE", `${payload.metrics.rmse} MW`],
      ["R² Score", String(payload.metrics.r2)],
      ["WAPE", `${payload.metrics.wape}%`],
    ]);
    const period = container.querySelector(".warning-banner strong");
    expect(period.textContent).toBe("2024-01-01 to 2024-12-31");

    const baselines = within(card("Naive baseline comparison (same test rows)")).getByRole("table");
    expect(within(baselines).getAllByRole("row")).toHaveLength(Object.keys(payload.baselines).length + 1);
    for (const [name, metrics] of Object.entries(payload.baselines)) {
      expect(rowCells(baselines, new RegExp(`^${name} `))).toEqual([
        name, ...[metrics.mae, metrics.rmse, metrics.r2, metrics.wape].map(String),
      ]);
    }

    const horizons = within(card("Horizon-specific evaluation")).getByRole("table");
    const oneStep = payload.horizon_metrics.one_step_observed_lag;
    expect(rowCells(horizons, /^Observed-lag one-step /)).toEqual([
      "Observed-lag one-step", String(oneStep.mae), String(oneStep.rmse), `${oneStep.wape}%`,
      oneStep.scored_rows == null ? "—" : String(oneStep.scored_rows),
    ]);
    const recursive = payload.horizon_metrics.recursive_multi_step;
    expect(within(horizons).getAllByRole("row")).toHaveLength(Object.keys(recursive).length + 2);
    for (const [horizon, result] of Object.entries(recursive)) {
      expect(rowCells(horizons, new RegExp(`^Recursive ${horizon}h `))).toEqual([
        `Recursive ${horizon}h`, String(result.metrics.mae), String(result.metrics.rmse),
        `${result.metrics.wape}%`, String(result.scored_rows),
      ]);
    }
    expect(screen.getByText(/not interchangeable/)).toBeTruthy();
    expect(screen.queryByText("Loading model performance...")).toBeNull();
  });
});

describe.each([
  ["DemandAnalysis", DemandAnalysis, "Loading demand analysis...", "Demand by Hour of Day"],
  ["ModelPerformance", ModelPerformance, "Loading model performance...", "Horizon-specific evaluation"],
])("%s failures", (name, Page, loading, content) => {
  it.each([
    ["backend failure", () => fetch.mockResolvedValue({
      ok: false, status: 503, json: async () => ({ detail: "Diagnostics are temporarily unavailable" }),
    }), "Diagnostics are temporarily unavailable"],
    ["network failure", () => fetch.mockRejectedValue(new Error("Network connection lost")), "Network connection lost"],
    ["invalid JSON", () => fetch.mockResolvedValue({
      ok: true, json: async () => { throw new SyntaxError("Unexpected token '<'"); },
    }), "Backend returned an invalid JSON response"],
  ])("replaces loading with a useful error after %s", async (scenario, fail, message) => {
    fail();
    render(<Page />);
    expect(screen.getByText(loading)).toBeTruthy();
    expect(await screen.findByText(`Failed to load: ${message}`, { exact: false })).toBeTruthy();
    expect(screen.queryByText(loading)).toBeNull();
    expect(screen.queryByText(content, { exact: true })).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
    if (name === "ModelPerformance") {
      expect(screen.getByRole("button", { name: "Retry backend connection" })).toBeTruthy();
    }
  });
});
