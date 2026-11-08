import { useQuery } from "@tanstack/react-query";
import { api, type AnomalyDetails, type ApiAlert, type ApiAnomaly, type Page } from "@/lib/api";
import { useAccount } from "@/hooks/use-account";
import type { Reading } from "@/data/hives";

/** The rule that turns an anomaly into a warning to review (US17); never critical, never notified. */
export const ANOMALY_RULE = "anomaly_detected";

export type Chart = "temperature" | "humidity" | "weight";

export const LEVEL_LABELS: Record<ApiAnomaly["level"], string> = {
  info: "Unusual",
  warning: "Very unusual",
};

/** The chart a window belongs on, from its kind ("temp_in_high"); null: a model could not say, so all. */
export function chartOf(kind: string | null): Chart | null {
  if (kind?.startsWith("temp_in")) return "temperature";
  if (kind?.startsWith("rh_in")) return "humidity";
  if (kind?.startsWith("weight")) return "weight";
  return null;
}

/** Anomaly windows that overlap the period on screen, from every model, newest first. */
export function useAnomalies(hiveId: string, range: "24h" | "7d") {
  const { user } = useAccount();
  return useQuery({
    queryKey: ["anomalies", hiveId, range],
    enabled: !!user,
    queryFn: () => {
      const start = new Date(Date.now() - (range === "24h" ? 1 : 7) * 86_400_000);
      return api<ApiAnomaly[]>(
        `/api/v1/hives/${hiveId}/anomalies?start=${encodeURIComponent(start.toISOString())}`,
      );
    },
  });
}

export type Warning = { alertId: string; title: string; details: AnomalyDetails };

/** The hive's anomaly warnings not yet resolved: the "to review" list on the hive page. */
export function useAnomalyWarnings(hiveId: string) {
  const { user } = useAccount();
  return useQuery({
    queryKey: ["alerts", "anomalies", hiveId],
    enabled: !!user,
    queryFn: async (): Promise<Warning[]> => {
      const pages = await Promise.all(
        (["open", "acknowledged"] as const).map((state) =>
          api<Page<ApiAlert>>(`/api/v1/alerts?hive_id=${hiveId}&state=${state}&limit=50`),
        ),
      );
      return pages
        .flatMap((p) => p.items)
        .filter((a) => a.rule_id === ANOMALY_RULE)
        .map((a) => ({
          alertId: a.id,
          title: a.title,
          details: a.details as unknown as AnomalyDetails,
        }));
    },
  });
}

export type Band = { x1: string; x2: string; level: ApiAnomaly["level"] };

/**
 * Where to shade the windows of one chart on its hourly rows: from the first row inside a window to the
 * last one. A window with no row on screen is left out.
 */
export function bands(rows: Reading[], windows: ApiAnomaly[], chart: Chart): Band[] {
  const out: Band[] = [];
  for (const w of windows) {
    const target = chartOf(w.kind);
    if (target !== null && target !== chart) continue;
    const start = Date.parse(w.start);
    const end = Date.parse(w.end);
    const inside = rows.filter((r) => {
      const t = Date.parse(r.ts);
      return t >= start && t < end;
    });
    const first = inside[0];
    const last = inside.at(-1);
    if (first && last) out.push({ x1: first.ts, x2: last.ts, level: w.level });
  }
  return out;
}

/** "36.5 °C, usually 35.0 °C · for 3 h" */
export function describe(d: AnomalyDetails): string {
  const digits = d.unit === "kg/h" ? 2 : 1;
  const sign = d.unit === "kg/h" && d.value > 0 ? "+" : "";
  const hours = Math.max(
    1,
    Math.round((Date.parse(d.window_end) - Date.parse(d.window_start)) / 3_600_000),
  );
  return (
    `${sign}${d.value.toFixed(digits)} ${d.unit}, usually ${d.expected.toFixed(digits)} ${d.unit}` +
    ` · for ${hours} h`
  );
}
