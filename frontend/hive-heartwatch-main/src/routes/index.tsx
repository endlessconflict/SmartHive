import { createFileRoute, Link } from "@tanstack/react-router";
import { Bell, ChevronRight, Clock, Droplets, Thermometer } from "lucide-react";
import { useHives } from "@/data/hives";
import { StatusBadge } from "@/components/StatusBadge";
import { Loading, RequireLogin } from "@/components/RequireLogin";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Hives — Smart Hive" },
      {
        name: "description",
        content: "Check the status, temperature, humidity and alerts of your hives.",
      },
      { property: "og:title", content: "Hives — Smart Hive" },
      { property: "og:description", content: "The status of all your hives in one view." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: () => (
    <RequireLogin>
      <HivesPage />
    </RequireLogin>
  ),
});

function HivesPage() {
  const { data: hives, error } = useHives();
  if (!hives) return <Loading error={error} />;
  return (
    <main className="mx-auto min-h-screen max-w-6xl px-4 py-6 sm:px-6">
      <h1 className="mb-4 text-2xl font-bold">Hives</h1>
      {hives.length === 0 && (
        <p className="rounded-2xl bg-card p-5 text-muted-foreground ring-1 ring-border">
          No hives yet.{" "}
          <Link to="/gestion" className="font-semibold underline">
            Go to Setup
          </Link>{" "}
          to create an apiary and a hive and attach a node to it.
        </p>
      )}
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {hives.map((h) => (
          <li key={h.id}>
            <Link
              to="/colmena/$id"
              params={{ id: h.id }}
              className="block rounded-2xl bg-card p-5 shadow-sm ring-1 ring-border transition hover:shadow-md focus-visible:outline-3 focus-visible:outline-primary"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-lg font-bold">{h.name}</h2>
                  <p className="text-sm text-muted-foreground">
                    {h.location}
                    {h.simulated && " · simulated node"}
                  </p>
                </div>
                <ChevronRight className="size-6 text-muted-foreground" aria-hidden="true" />
              </div>
              <div className="mt-3">
                <StatusBadge status={h.status} />
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-xl bg-muted p-3">
                  <p className="flex items-center gap-1 text-sm text-muted-foreground">
                    <Thermometer className="size-4" />
                    Temperature
                  </p>
                  <p className="text-xl font-bold">{h.temperature ?? "—"} °C</p>
                </div>
                <div className="rounded-xl bg-muted p-3">
                  <p className="flex items-center gap-1 text-sm text-muted-foreground">
                    <Droplets className="size-4" />
                    Humidity
                  </p>
                  <p className="text-xl font-bold">{h.humidity ?? "—"} %</p>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between text-sm">
                <span className="flex items-center gap-1 text-muted-foreground">
                  <Clock className="size-4" />
                  {h.lastUpdate}
                </span>
                <span
                  className={`flex items-center gap-1 font-semibold ${h.openAlerts ? "text-danger" : "text-muted-foreground"}`}
                >
                  <Bell className="size-4" />
                  {h.openAlerts === 1 ? "1 alert" : `${h.openAlerts} alerts`}
                </span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
