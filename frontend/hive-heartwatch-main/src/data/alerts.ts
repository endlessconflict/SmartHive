import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { api, type ApiAlert, type ApiAlertDetail, type Page } from "@/lib/api";
import { useAccount } from "@/hooks/use-account";

export type AlertType =
  "varroa" | "beetle" | "hornet" | "offline" | "power" | "temperature" | "humidity" | "other";
export type AlertStatus = "new" | "in_progress" | "resolved";

export const ALERT_TYPE_LABELS: Record<AlertType, string> = {
  varroa: "Varroa mite",
  beetle: "Small hive beetle",
  hornet: "Asian hornet",
  offline: "Node offline",
  power: "Weak power supply",
  temperature: "Temperature out of range",
  humidity: "Humidity out of range",
  other: "Alert",
};

export const ALERT_STATUS_LABELS: Record<AlertStatus, string> = {
  new: "New",
  in_progress: "In progress",
  resolved: "Resolved",
};

const TYPES: Record<string, AlertType> = {
  varroa_high: "varroa",
  shb_detected: "beetle",
  hornet_detected: "hornet",
  node_offline: "offline",
  node_power_low: "power",
  temp_out_of_range: "temperature",
  rh_out_of_range: "humidity",
};

const STATES: Record<ApiAlert["state"], AlertStatus> = {
  open: "new",
  acknowledged: "in_progress",
  resolved: "resolved",
};

export type HiveAlert = {
  id: string;
  type: AlertType;
  title: string;
  severity: ApiAlert["severity"];
  hiveId: string | null;
  nodeId: string | null;
  confidence: number | null;
  date: string;
  openedAt: string;
  status: AlertStatus;
  note: string;
};

function toAlert(a: ApiAlert): HiveAlert {
  const conf = a.details["max_conf"];
  return {
    id: a.id,
    type: TYPES[a.rule_id] ?? "other",
    title: a.title,
    severity: a.severity,
    hiveId: a.hive_id,
    nodeId: a.node_id,
    confidence: typeof conf === "number" ? Math.round(conf * 100) : null,
    date: format(new Date(a.opened_at), "MMM d, yyyy, HH:mm"),
    openedAt: a.opened_at,
    status: STATES[a.state],
    note: a.resolution_note ?? "",
  };
}

export function useAlerts() {
  const { user } = useAccount();
  return useQuery({
    queryKey: ["alerts", "all"],
    enabled: !!user,
    queryFn: async () => (await api<Page<ApiAlert>>("/api/v1/alerts?limit=200")).items.map(toAlert),
  });
}

export function useAlert(id: string) {
  const { user } = useAccount();
  return useQuery({
    queryKey: ["alerts", "one", id],
    enabled: !!user,
    queryFn: async () => toAlert(await api<ApiAlertDetail>(`/api/v1/alerts/${id}`)),
  });
}

/** The API moves alerts forward only: new → in progress (acknowledge) → resolved (with an optional note). */
export function useUpdateAlert(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ status, note }: { status: AlertStatus; note?: string }) =>
      status === "in_progress"
        ? api(`/api/v1/alerts/${id}/acknowledge`, { method: "POST" })
        : api(`/api/v1/alerts/${id}/resolve`, {
            method: "POST",
            body: JSON.stringify({ note: note?.trim() || null }),
          }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["alerts"] });
      void client.invalidateQueries({ queryKey: ["hives"] });
    },
  });
}
