import { Activity, Bug, Thermometer, WifiOff, Zap } from "lucide-react";
import type { AlertType } from "@/data/alerts";

export function alertIcon(type: AlertType) {
  if (type === "offline") return { Icon: WifiOff, cls: "bg-offline-soft text-offline" };
  if (type === "power") return { Icon: Zap, cls: "bg-offline-soft text-offline" };
  if (type === "temperature" || type === "humidity")
    return { Icon: Thermometer, cls: "bg-warning-soft text-warning" };
  if (type === "anomaly") return { Icon: Activity, cls: "bg-muted text-warning" }; // calmer than an alert
  return { Icon: Bug, cls: "bg-warning-soft text-warning" };
}
