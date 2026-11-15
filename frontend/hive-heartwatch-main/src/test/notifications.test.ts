import { describe, expect, it } from "vitest";

import { toNotification, type ApiNotification } from "@/data/notifications";

const row = (over: Partial<ApiNotification> = {}): ApiNotification => ({
  id: 7,
  alert_id: "a1",
  hive_id: "h1",
  severity: "critical",
  title: "Hornet at the entrance",
  alert_state: "open",
  created_at: "2026-11-15T20:00:00Z",
  read_at: null,
  ...over,
});

describe("toNotification", () => {
  it("keeps the alert it belongs to and says how long ago it happened", () => {
    const n = toNotification(row());
    expect(n).toMatchObject({ id: 7, alertId: "a1", hiveId: "h1", severity: "critical", read: false });
    expect(n.ago).toMatch(/ago$/);
  });

  it("is read once the server has a read time", () => {
    expect(toNotification(row({ read_at: "2026-11-15T20:05:00Z" })).read).toBe(true);
  });
});
