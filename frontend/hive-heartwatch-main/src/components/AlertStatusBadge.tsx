import { ALERT_STATUS_LABELS, type AlertStatus } from "@/data/alerts";

const cls: Record<AlertStatus, string> = {
  new: "bg-danger-soft text-danger",
  in_progress: "bg-warning-soft text-warning",
  resolved: "bg-success-soft text-success",
};

export function AlertStatusBadge({ status }: { status: AlertStatus }) {
  return <span className={`inline-flex rounded-full px-3 py-1 text-sm font-semibold ${cls[status]}`}>{ALERT_STATUS_LABELS[status]}</span>;
}
