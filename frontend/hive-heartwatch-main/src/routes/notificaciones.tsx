import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { useHives } from "@/data/hives";
import { useInbox, useMarkRead, type Notification } from "@/data/notifications";
import { Button } from "@/components/ui/button";
import { Loading, RequireLogin } from "@/components/RequireLogin";

export const Route = createFileRoute("/notificaciones")({
  head: () => ({
    meta: [
      { title: "Inbox — Smart Hive" },
      { name: "description", content: "Notifications about your hives, newest first." },
      { property: "og:title", content: "Inbox — Smart Hive" },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: () => (
    <RequireLogin>
      <InboxPage />
    </RequireLogin>
  ),
});

const SEVERITY: Record<Notification["severity"], string> = {
  critical: "bg-danger-soft text-danger",
  warning: "bg-warning-soft text-warning",
  info: "bg-success-soft text-success",
};

function InboxPage() {
  const inbox = useInbox();
  const hives = useHives().data ?? [];
  const mark = useMarkRead();
  const navigate = useNavigate();
  if (!inbox.data) return <Loading error={inbox.error} />;
  const { items, unread } = inbox.data;

  async function open(n: Notification) {
    if (!n.read) await mark.one.mutateAsync(n.id);
    await navigate({ to: "/alertas/$id", params: { id: n.alertId } });
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Inbox</h1>
        <Button
          variant="outline"
          className="min-h-12"
          disabled={unread === 0 || mark.all.isPending}
          onClick={() => mark.all.mutate()}
        >
          Mark all as read
        </Button>
      </div>
      <p className="mb-4 text-muted-foreground" aria-live="polite">
        {unread === 0 ? "You are up to date." : `${unread} unread`}
      </p>
      {items.length === 0 && (
        <p className="rounded-2xl bg-card p-5 text-muted-foreground ring-1 ring-border">
          Nothing here yet. Alerts about your hives will show up as they happen.
        </p>
      )}
      <ul className="space-y-3">
        {items.map((n) => {
          const hive = hives.find((h) => h.id === n.hiveId);
          return (
            <li key={n.id}>
              <button
                type="button"
                onClick={() => void open(n)}
                className={`flex w-full items-center gap-3 rounded-2xl bg-card p-4 text-left ring-1 ring-border hover:shadow-md ${n.read ? "" : "border-l-4 border-l-danger"}`}
              >
                <span
                  className={`inline-flex shrink-0 rounded-full px-3 py-1 text-sm font-semibold ${SEVERITY[n.severity]}`}
                >
                  {n.severity}
                </span>
                <div className="min-w-0 flex-1">
                  <p className={n.read ? "font-medium" : "font-bold"}>{n.title}</p>
                  <p className="text-sm text-muted-foreground">
                    {hive?.name ?? "Hive"} · {n.ago}
                    {n.alertState === "resolved" && " · resolved"}
                  </p>
                </div>
                {!n.read && <span className="sr-only">Unread</span>}
                <ChevronRight className="size-6 shrink-0 text-muted-foreground" />
              </button>
            </li>
          );
        })}
      </ul>
      <p className="mt-6 text-sm text-muted-foreground">
        <Link to="/alertas" className="underline">
          All alerts
        </Link>
      </p>
    </main>
  );
}
