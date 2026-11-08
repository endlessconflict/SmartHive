import { describe as group, expect, it } from "vitest";

import { bands, chartOf, describe } from "@/data/anomalies";
import type { Reading } from "@/data/hives";
import type { AnomalyDetails, ApiAnomaly } from "@/lib/api";

const row = (hour: number): Reading => {
  const ts = `2026-11-08T${String(hour).padStart(2, "0")}:00:00Z`;
  return { ts, time: ts.slice(11, 16), temperature: 35, humidity: 58, weight: null };
};
const rows = [8, 9, 10, 11, 12].map(row);

const window = (start: string, end: string, extra: Partial<ApiAnomaly> = {}): ApiAnomaly => ({
  id: "w1",
  hive_id: "h1",
  start,
  end,
  score: 5,
  kind: "temp_in_high",
  model: "robust-z@1",
  level: "info",
  ...extra,
});

group("bands", () => {
  it("shades from the first to the last hour inside the window", () => {
    const w = window("2026-11-08T10:00:00+00:00", "2026-11-08T12:00:00+00:00", {
      level: "warning",
    });
    expect(bands(rows, [w], "temperature")).toEqual([
      { x1: "2026-11-08T10:00:00Z", x2: "2026-11-08T11:00:00Z", level: "warning" },
    ]);
  });

  it("puts a window only on its own chart", () => {
    const w = window("2026-11-08T10:00:00Z", "2026-11-08T12:00:00Z");
    expect(bands(rows, [w], "humidity")).toEqual([]);
  });

  it("puts a window a model could not name on every chart", () => {
    const w = window("2026-11-08T10:00:00Z", "2026-11-08T12:00:00Z", { kind: null });
    expect(bands(rows, [w], "humidity")).toHaveLength(1);
    expect(bands(rows, [w], "weight")).toHaveLength(1);
  });

  it("clips a window that started before the chart", () => {
    const w = window("2026-11-07T20:00:00Z", "2026-11-08T09:30:00Z");
    expect(bands(rows, [w], "temperature")).toEqual([
      { x1: "2026-11-08T08:00:00Z", x2: "2026-11-08T09:00:00Z", level: "info" },
    ]);
  });

  it("leaves out a window with no hour on screen", () => {
    const w = window("2026-11-08T20:00:00Z", "2026-11-08T22:00:00Z");
    expect(bands(rows, [w], "temperature")).toEqual([]);
  });
});

group("chartOf", () => {
  it("reads the chart from the kind", () => {
    expect(["temp_in_high", "rh_in_low", "weight_low", "swarming", null].map(chartOf)).toEqual([
      "temperature",
      "humidity",
      "weight",
      null,
      null,
    ]);
  });
});

group("describe", () => {
  const details = (extra: Partial<AnomalyDetails> = {}): AnomalyDetails => ({
    quantity: "temp_in",
    level: "info",
    window_start: "2026-11-08T10:00:00Z",
    window_end: "2026-11-08T13:00:00Z",
    value: 36.52,
    expected: 35.01,
    unit: "°C",
    ...extra,
  });

  it("says what was seen against what is usual, and for how long", () => {
    expect(describe(details())).toBe("36.5 °C, usually 35.0 °C · for 3 h");
  });

  it("signs a weight change", () => {
    const gain = details({ quantity: "weight", unit: "kg/h", value: 0.8, expected: 0.01 });
    expect(describe(gain)).toBe("+0.80 kg/h, usually 0.01 kg/h · for 3 h");
  });
});
