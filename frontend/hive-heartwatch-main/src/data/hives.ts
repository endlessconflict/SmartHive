import { useQuery } from "@tanstack/react-query";
import { format, formatDistanceToNow } from "date-fns";
import {
  api,
  type ApiAlert,
  type ApiHive,
  type Apiary,
  type Page,
  type Point,
  type Series,
} from "@/lib/api";
import { useAccount } from "@/hooks/use-account";
import { ANOMALY_RULE } from "@/data/anomalies";

export type HiveStatus = "healthy" | "attention" | "critical" | "offline";

export type Hive = {
  id: string;
  name: string;
  location: string;
  status: HiveStatus;
  temperature: number | null;
  humidity: number | null;
  weight: number | null; // null also for a node without a scale
  lastUpdate: string;
  openAlerts: number;
  openAnomalies: number; // warnings to review, not alerts: they never change the status
  nodeId: string | null;
  simulated: boolean;
};

export const STATUS_LABELS: Record<HiveStatus, string> = {
  healthy: "Healthy",
  attention: "Needs attention",
  critical: "Critical",
  offline: "Offline",
};

/**
 * Alerts still to be handled (open or acknowledged), shared by the hive cards and the header badge.
 * Anomalies are left out: they are shown on the hive page as something to review, without pressure (US17).
 */
export function useActiveAlerts() {
  const { user } = useAccount();
  return useQuery({
    queryKey: ["alerts", "active"],
    enabled: !!user,
    queryFn: async () => {
      const [open, acknowledged] = await Promise.all([
        api<Page<ApiAlert>>("/api/v1/alerts?state=open&limit=200"),
        api<Page<ApiAlert>>("/api/v1/alerts?state=acknowledged&limit=200"),
      ]);
      return [...open.items, ...acknowledged.items].filter((a) => a.rule_id !== ANOMALY_RULE);
    },
  });
}

function status(h: ApiHive, alerts: ApiAlert[]): HiveStatus {
  if (!h.node_id || h.node_status === "offline") return "offline";
  const mine = alerts.filter((a) => a.hive_id === h.id);
  if (mine.some((a) => a.severity === "critical")) return "critical";
  return mine.length ? "attention" : "healthy";
}

function toHive(h: ApiHive, apiaries: Apiary[], alerts: ApiAlert[]): Hive {
  const temp = h.latest["temp_in"];
  const rh = h.latest["rh_in"];
  const weight = h.latest["weight"];
  const newest = [temp, rh, weight]
    .filter(Boolean)
    .map((l) => l!.ts)
    .sort()
    .at(-1);
  return {
    id: h.id,
    name: h.name,
    location: apiaries.find((a) => a.id === h.apiary_id)?.name ?? "",
    status: status(h, alerts),
    temperature: temp?.value ?? null,
    humidity: rh?.value ?? null,
    weight: weight?.value ?? null,
    lastUpdate: newest ? formatDistanceToNow(new Date(newest), { addSuffix: true }) : "no data yet",
    openAlerts: h.open_alerts,
    openAnomalies: h.open_anomalies ?? 0,
    nodeId: h.node_id,
    simulated: h.simulated,
  };
}

export function useHives() {
  const { user } = useAccount();
  const alerts = useActiveAlerts();
  const query = useQuery({
    queryKey: ["hives"],
    enabled: !!user,
    queryFn: async () => {
      const [hives, apiaries] = await Promise.all([
        api<Page<ApiHive>>("/api/v1/hives?limit=200"),
        api<Page<Apiary>>("/api/v1/apiaries?limit=200"),
      ]);
      return { hives: hives.items, apiaries: apiaries.items };
    },
  });
  const data = query.data?.hives.map((h) => toHive(h, query.data.apiaries, alerts.data ?? []));
  return { ...query, data };
}

export function useHive(id: string) {
  const hives = useHives();
  return { ...hives, data: hives.data?.find((h) => h.id === id) };
}

export type Reading = {
  ts: string; // start of the hour, ISO: the x of the charts, and where anomaly bands snap to
  time: string;
  temperature: number | null;
  humidity: number | null;
  weight: number | null;
};

const round = (v: number | null, decimals: number) => {
  if (v === null) return null;
  const f = 10 ** decimals;
  return Math.round(v * f) / f;
};

/** One row per timestamp, oldest first. A quantity with no value at that time stays null. */
export function mergeSeries(
  series: { temperature: Point[]; humidity: Point[]; weight: Point[] },
  label: (ts: string) => string,
): Reading[] {
  const byTs = new Map<string, Reading>();
  const add = (points: Point[], field: "temperature" | "humidity" | "weight", decimals: number) => {
    for (const p of points) {
      const row = byTs.get(p.ts) ?? {
        ts: p.ts,
        time: label(p.ts),
        temperature: null,
        humidity: null,
        weight: null,
      };
      byTs.set(p.ts, { ...row, [field]: round(p.value, decimals) });
    }
  };
  add(series.temperature, "temperature", 1);
  add(series.humidity, "humidity", 1);
  add(series.weight, "weight", 2); // 10 g, the resolution of the scale
  return [...byTs.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, r]) => r);
}

/** Hourly means; the hour label for 24 h, the day for 7 days. */
export function useHistory(hiveId: string, range: "24h" | "7d") {
  const { user } = useAccount();
  return useQuery({
    queryKey: ["readings", hiveId, range],
    enabled: !!user,
    queryFn: async (): Promise<Reading[]> => {
      const end = new Date();
      const start = new Date(end.getTime() - (range === "24h" ? 1 : 7) * 86_400_000);
      const series = (quantity: string) =>
        api<Series>(
          `/api/v1/hives/${hiveId}/readings?quantity=${quantity}&bucket=1h` +
            `&start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`,
        );
      const [temp, rh, weight] = await Promise.all([
        series("temp_in"),
        series("rh_in"),
        series("weight"),
      ]);
      return mergeSeries(
        { temperature: temp.points, humidity: rh.points, weight: weight.points },
        (ts) => format(new Date(ts), range === "24h" ? "HH:mm" : "EEE d, HH:mm"),
      );
    },
  });
}
