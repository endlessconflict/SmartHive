import type { ApiAlert } from "@/lib/api";

/** Alert rules that come with a picture, and the image reason the node keeps it under. */
export const PICTURE_ALERTS: Record<string, { reason: string; title: string }> = {
  hornet_detected: { reason: "threat", title: "Hornet alert" },
  varroa_high: { reason: "varroa", title: "Varroa alert" },
};

/** Which pictures the hive page shows: one per open hornet or Varroa alert, else only the latest one. */
export function pictureAlerts(alerts: ApiAlert[], hiveId: string): ApiAlert[] {
  const mine = alerts.filter((a) => a.hive_id === hiveId && a.rule_id in PICTURE_ALERTS);
  const newest = new Map<string, ApiAlert>();
  for (const a of mine) {
    const seen = newest.get(a.rule_id);
    if (!seen || a.opened_at > seen.opened_at) newest.set(a.rule_id, a);
  }
  return Object.keys(PICTURE_ALERTS).flatMap((rule) => newest.get(rule) ?? []);
}
