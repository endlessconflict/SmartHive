import { createFileRoute, Link } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { ALERT_TYPE_LABELS, useAlerts } from "@/data/alerts";
import { useHives } from "@/data/hives";
import { AlertStatusBadge } from "@/components/AlertStatusBadge";
import { alertIcon } from "@/components/alert-icon";
import { Loading, RequireLogin } from "@/components/RequireLogin";

export const Route = createFileRoute("/alertas/")({
  head: () => ({
    meta: [
      { title: "Alerts — Smart Hive" },
      { name: "description", content: "Detected pests and offline nodes in your hives." },
      { property: "og:title", content: "Alerts — Smart Hive" },
      { property: "og:description", content: "List of pest and connection alerts." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: () => (
    <RequireLogin>
      <AlertsPage />
    </RequireLogin>
  ),
});

function AlertsPage() {
  const { data: alerts, error } = useAlerts();
  const hives = useHives().data ?? [];
  if (!alerts) return <Loading error={error} />;
  return (
    <main className="mx-auto max-w-4xl px-4 py-6 sm:px-6">
      <h1 className="mb-4 text-2xl font-bold">Alerts</h1>
      {alerts.length === 0 && (
        <p className="rounded-2xl bg-card p-5 text-muted-foreground ring-1 ring-border">
          No alerts. All quiet.
        </p>
      )}
      <ul className="space-y-3">
        {alerts.map((a) => {
          const hive = hives.find((h) => h.id === a.hiveId);
          const { Icon, cls } = alertIcon(a.type);
          return (
            <li key={a.id}>
              <Link
                to="/alertas/$id"
                params={{ id: a.id }}
                className={`flex items-center gap-3 rounded-2xl bg-card p-4 ring-1 ring-border hover:shadow-md ${a.status === "new" ? "border-l-4 border-l-danger" : ""}`}
              >
                <span className={`grid size-12 shrink-0 place-items-center rounded-xl ${cls}`}>
                  <Icon className="size-6" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="font-bold">{ALERT_TYPE_LABELS[a.type]}</p>
                  <p className="text-sm text-muted-foreground">
                    {hive?.name ?? a.nodeId}
                    {a.confidence !== null && ` · ${a.confidence} %`} · {a.date}
                  </p>
                  <div className="mt-2">
                    <AlertStatusBadge status={a.status} />
                  </div>
                </div>
                <ChevronRight className="size-6 shrink-0 text-muted-foreground" />
              </Link>
            </li>
          );
        })}
      </ul>
    </main>
  );
}
