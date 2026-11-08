import { describe, expect, it } from "vitest";

import { mergeSeries } from "@/data/hives";
import type { Point } from "@/lib/api";

const point = (ts: string, value: number | null): Point => ({
  ts,
  value,
  min: null,
  max: null,
  n: 1,
});

describe("mergeSeries", () => {
  it("joins the quantities by timestamp, oldest first, rounding weight to 10 g", () => {
    const rows = mergeSeries(
      {
        temperature: [point("2026-11-06T11:00:00Z", 35.04), point("2026-11-06T10:00:00Z", 34.96)],
        humidity: [point("2026-11-06T10:00:00Z", 58)],
        weight: [point("2026-11-06T10:00:00Z", 41.2371)],
      },
      (ts) => ts.slice(11, 16),
    );
    expect(rows).toEqual([
      {
        ts: "2026-11-06T10:00:00Z",
        time: "10:00",
        temperature: 35,
        humidity: 58,
        weight: 41.24,
      },
      {
        ts: "2026-11-06T11:00:00Z",
        time: "11:00",
        temperature: 35,
        humidity: null,
        weight: null,
      },
    ]);
  });

  it("gives a row to a weight with no other reading at that time", () => {
    const rows = mergeSeries(
      { temperature: [], humidity: [], weight: [point("2026-11-06T10:00:00Z", 41.5)] },
      (ts) => ts,
    );
    expect(rows.map((r) => r.weight)).toEqual([41.5]);
    expect(rows[0]?.temperature).toBeNull();
  });
});
