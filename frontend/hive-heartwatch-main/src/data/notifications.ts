import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { api, type Page } from "@/lib/api";
import { useAccount } from "@/hooks/use-account";

/** One row of GET /api/v1/me/notifications: the in-app inbox (US11.3). */
export type ApiNotification = {
  id: number;
  alert_id: string;
  hive_id: string | null;
  severity: "info" | "warning" | "critical";
  title: string;
  alert_state: "open" | "acknowledged" | "resolved";
  created_at: string;
  read_at: string | null;
};

type InboxPage = Page<ApiNotification> & { unread: number };

export type Notification = {
  id: number;
  alertId: string;
  hiveId: string | null;
  severity: ApiNotification["severity"];
  title: string;
  alertState: ApiNotification["alert_state"];
  ago: string;
  read: boolean;
};

export function toNotification(n: ApiNotification, now = new Date()): Notification {
  return {
    id: n.id,
    alertId: n.alert_id,
    hiveId: n.hive_id,
    severity: n.severity,
    title: n.title,
    alertState: n.alert_state,
    ago: formatDistanceToNow(new Date(n.created_at), { addSuffix: true, includeSeconds: true }),
    read: n.read_at !== null,
  };
}

export function useInbox() {
  const { user } = useAccount();
  return useQuery({
    queryKey: ["notifications"],
    enabled: !!user,
    queryFn: async () => {
      const page = await api<InboxPage>("/api/v1/me/notifications?limit=100");
      return { items: page.items.map((n) => toNotification(n)), unread: page.unread };
    },
  });
}

export function useMarkRead() {
  const client = useQueryClient();
  const done = () => void client.invalidateQueries({ queryKey: ["notifications"] });
  return {
    one: useMutation({
      mutationFn: (id: number) => api(`/api/v1/me/notifications/${id}/read`, { method: "POST" }),
      onSuccess: done,
    }),
    all: useMutation({
      mutationFn: () => api("/api/v1/me/notifications/read-all", { method: "POST" }),
      onSuccess: done,
    }),
  };
}
