import { AlertTriangle, CheckCircle2, WifiOff, XOctagon } from "lucide-react";
import { STATUS_LABELS, type HiveStatus } from "@/data/hives";

const styles: Record<HiveStatus, { cls: string; Icon: typeof CheckCircle2 }> = {
  healthy: { cls: "bg-success-soft text-success", Icon: CheckCircle2 },
  attention: { cls: "bg-warning-soft text-warning", Icon: AlertTriangle },
  critical: { cls: "bg-danger-soft text-danger", Icon: XOctagon },
  offline: { cls: "bg-offline-soft text-offline", Icon: WifiOff },
};

export function StatusBadge({ status }: { status: HiveStatus }) {
  const { cls, Icon } = styles[status];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-semibold ${cls}`}>
      <Icon className="size-4" aria-hidden="true" />
      {STATUS_LABELS[status]}
    </span>
  );
}
