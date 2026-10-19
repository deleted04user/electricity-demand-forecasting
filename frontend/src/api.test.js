import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let api;

beforeEach(async () => {
  vi.resetModules();
  vi.stubEnv("VITE_API_BASE_URL", "");
  vi.stubGlobal("fetch", vi.fn());
  ({ api } = await import("./api"));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("bounded API requests", () => {
  function abortable(signal) {
    return new Promise((_resolve, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
    });
  }

  it("aborts a request that never receives response headers", async () => {
    vi.useFakeTimers();
    fetch.mockImplementation((_url, { signal }) => abortable(signal));
    const result = api.meta().catch((error) => error.message);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(await result).toBe("Backend request timed out after 30 seconds. Please retry.");
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("also aborts a stalled response body after headers arrive", async () => {
    vi.useFakeTimers();
    fetch.mockImplementation((_url, { signal }) => Promise.resolve({ ok: true, json: () => abortable(signal) }));
    const result = api.overview().catch((error) => error.message);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(await result).toContain("timed out after 30 seconds");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("clears deadlines after successful responses and ordinary backend errors", async () => {
    vi.useFakeTimers();
    fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ ready: true }) });
    expect(await api.meta()).toEqual({ ready: true });
    expect(vi.getTimerCount()).toBe(0);
    fetch.mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ detail: "Unavailable" }) });
    await expect(api.meta()).rejects.toThrow("Unavailable");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("keeps simultaneous request deadlines independent", async () => {
    vi.useFakeTimers();
    let resolveSecond;
    fetch.mockImplementationOnce((_url, { signal }) => abortable(signal));
    const first = api.meta().catch((error) => error.message);
    await vi.advanceTimersByTimeAsync(15_000);
    fetch.mockImplementationOnce(() => new Promise((resolve) => { resolveSecond = resolve; }));
    const second = api.overview();
    await vi.advanceTimersByTimeAsync(15_000);
    expect(await first).toContain("timed out");
    expect(fetch.mock.calls[1][1].signal.aborted).toBe(false);
    resolveSecond({ ok: true, json: async () => ({ ready: true }) });
    expect(await second).toEqual({ ready: true });
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("API deployment and request handling", () => {
  it("uses the browser origin by default for a proxied deployment", async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => ({ status: "ready" }) });
    expect(await api.meta()).toEqual({ status: "ready" });
    expect(String(fetch.mock.calls[0][0])).toBe(`${window.location.origin}/api/meta`);
  });

  it("supports a separately hosted API and encodes query parameters", async () => {
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example.test///");
    vi.resetModules();
    ({ api } = await import("./api"));
    fetch.mockResolvedValue({ ok: true, json: async () => ({ predicted: 2500 }) });
    await api.forecast("2025-01-01&hour=23", 12);
    const url = new URL(fetch.mock.calls[0][0]);
    expect(url.origin).toBe("https://api.example.test");
    expect(url.pathname).toBe("/api/forecast");
    expect(url.searchParams.get("date")).toBe("2025-01-01&hour=23");
    expect(url.searchParams.getAll("hour")).toEqual(["12"]);
  });

  it("posts a future forecast as JSON to the same origin", async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => ({ forecast: [] }) });
    await api.futureForecast("2025-01-01 00:00:00", 24);
    const [url, options] = fetch.mock.calls[0];
    expect(String(url)).toBe(`${window.location.origin}/api/forecast/future`);
    expect(options.method).toBe("POST");
    expect(options.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(options.body)).toEqual({ start: "2025-01-01 00:00:00", horizon: 24 });
  });

  it("preserves a useful backend error message", async () => {
    fetch.mockResolvedValue({ ok: false, status: 404, json: async () => ({ detail: "No historical data for this hour" }) });
    await expect(api.forecast("2025-01-01", 0)).rejects.toThrow("No historical data for this hour");
  });

  it("turns structured validation details into a renderable error", async () => {
    fetch.mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: [{ msg: "Invalid hour" }] }) });
    await expect(api.forecast("2025-01-01", 99)).rejects.toThrow("Request failed: 422");
  });

  it("reports the HTTP status when a proxy sends a non-JSON error", async () => {
    fetch.mockResolvedValue({ ok: false, status: 502, json: async () => { throw new SyntaxError("Unexpected token '<'"); } });
    await expect(api.futureForecast("2025-01-01 00:00:00", 24)).rejects.toThrow("Request failed: 502");
  });

  it("reports an invalid successful response without crashing a page", async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => { throw new SyntaxError("Unexpected token '<'"); } });
    await expect(api.overview()).rejects.toThrow("Backend returned an invalid JSON response");
  });
});
