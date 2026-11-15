import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ApiAlert, ApiImage } from "@/lib/api";

const state = vi.hoisted(() => ({
  alerts: [] as ApiAlert[],
  images: {} as Record<string, ApiImage | null>, // by reason, "any" for the newest of all
  asked: [] as string[],
}));

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => <a>{children}</a>,
}));
vi.mock("@/data/hives", () => ({
  useActiveAlerts: () => ({ data: state.alerts, isPending: false }),
}));
vi.mock("@/data/images", async (real) => ({
  ...(await real<typeof import("@/data/images")>()),
  useImageUrl: (id: string | undefined) => (id ? `blob:${id}` : null),
  useLatestImage: (_hive: string, reason?: string, enabled = true) => {
    if (enabled) state.asked.push(reason ?? "any");
    return {
      data: enabled ? (state.images[reason ?? "any"] ?? null) : undefined,
      isPending: false,
    };
  },
}));

import { HiveImage } from "@/components/HiveImage";
import { pictureAlerts } from "@/data/alert-pictures";

const alert = (id: string, rule_id: string, hive_id = "h1", opened_at = "2026-11-14T10:00:00Z") =>
  ({ id, rule_id, hive_id, opened_at, title: `${rule_id} title` }) as ApiAlert;
const image = (id: string, reason: string) =>
  ({
    id,
    reason,
    captured_at: "2026-11-14T10:00:00Z",
    width: 160,
    height: 280,
    objects: [],
  }) as unknown as ApiImage;
const shown = () => screen.queryAllByRole("img").map((i) => i.getAttribute("src"));

describe("hive page picture", () => {
  beforeEach(() => {
    state.alerts = [];
    state.images = {
      any: image("newest", "periodic"),
      threat: image("hornet-1", "threat"),
      varroa: image("v-1", "varroa"),
    };
    state.asked = [];
  });

  it("without a hornet or Varroa alert shows only the latest image", () => {
    state.alerts = [alert("a1", "temp_out_of_range")];
    render(<HiveImage hiveId="h1" />);
    expect(shown()).toEqual(["blob:newest"]);
    expect(screen.getByText("Latest entrance image")).toBeTruthy();
  });

  it("with a hornet alert shows the alert's picture, not the latest", () => {
    state.alerts = [alert("a1", "hornet_detected")];
    render(<HiveImage hiveId="h1" />);
    expect(shown()).toEqual(["blob:hornet-1"]);
    expect(state.asked).not.toContain("any");
    expect(screen.getByText(/Hornet alert/)).toBeTruthy();
  });

  it("with both alerts shows both pictures, the hornet first", () => {
    state.alerts = [alert("a2", "varroa_high"), alert("a1", "hornet_detected")];
    render(<HiveImage hiveId="h1" />);
    expect(shown()).toEqual(["blob:hornet-1", "blob:v-1"]);
  });

  it("says when the alert's picture has not arrived yet", () => {
    state.alerts = [alert("a1", "hornet_detected")];
    state.images["threat"] = null;
    render(<HiveImage hiveId="h1" />);
    expect(screen.getByText("The picture of this alert has not arrived yet.")).toBeTruthy();
  });

  it("keeps one alert per kind and only the hive's own", () => {
    const picked = pictureAlerts(
      [
        alert("old", "hornet_detected", "h1", "2026-11-14T08:00:00Z"),
        alert("new", "hornet_detected", "h1", "2026-11-14T09:00:00Z"),
        alert("other", "varroa_high", "h2"),
        alert("t", "temp_out_of_range"),
      ],
      "h1",
    );
    expect(picked.map((a) => a.id)).toEqual(["new"]);
  });
});
