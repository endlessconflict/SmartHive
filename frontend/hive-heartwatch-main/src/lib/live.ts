import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { getAccessToken, restoreSession } from "@/lib/api";

const RETRY_MS = 5000;

/**
 * /api/v1/ws pushes readings, detections, alerts and node status for the subscribed hives.
 * Each message only marks the matching queries stale; React Query refetches what is on screen.
 */
export function useLiveUpdates(hiveIds: string[]) {
  const client = useQueryClient();
  const key = hiveIds.slice().sort().join(",");

  useEffect(() => {
    if (!key) return;
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;

    const connect = async () => {
      if (!getAccessToken() && !(await restoreSession())) return;
      if (stopped) return;
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${proto}://${window.location.host}/api/v1/ws`);
      socket.onopen = () => socket?.send(JSON.stringify({ op: "auth", token: getAccessToken() }));
      socket.onmessage = (e) => {
        const m = JSON.parse(e.data);
        const stale = (...queryKey: unknown[]) => void client.invalidateQueries({ queryKey });
        switch (m.type) {
          case "ready":
            socket?.send(JSON.stringify({ op: "subscribe", hives: key.split(",") }));
            break;
          case "reading":
          case "backfill":
            stale("readings", m.hive_id);
            stale("hives");
            break;
          case "detection":
            stale("images", m.hive_id);
            stale("hives");
            break;
          case "alert":
            stale("alerts");
            stale("hives");
            break;
          case "node_status":
            stale("hives");
            break;
          case "resync":
            void client.invalidateQueries();
        }
      };
      // 4401: the token expired; the retry renews it. Any other close: reconnect and catch up.
      socket.onclose = (e) => {
        if (stopped) return;
        if (e.code === 4401) void restoreSession();
        void client.invalidateQueries();
        timer = setTimeout(connect, RETRY_MS);
      };
    };

    void connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      socket?.close();
    };
  }, [key, client]);
}
