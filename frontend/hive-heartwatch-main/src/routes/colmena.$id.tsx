import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { ArrowLeft, Camera, Droplets, Thermometer, WifiOff } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useHistory, useHive } from "@/data/hives";
import { detections, useImageUrl, useLatestImage } from "@/data/images";
import { StatusBadge } from "@/components/StatusBadge";
import { Loading, RequireLogin } from "@/components/RequireLogin";
import { DetectionImage } from "@/components/DetectionImage";

export const Route = createFileRoute("/colmena/$id")({
  head: () => ({
    meta: [
      { title: "Hive — Smart Hive" },
      { name: "description", content: "Temperature, humidity and the hive entrance image." },
      { property: "og:title", content: "Hive — Smart Hive" },
      { property: "og:description", content: "Hive details and pest detections." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: () => (
    <RequireLogin>
      <HiveDetail />
    </RequireLogin>
  ),
});

function HiveDetail() {
  const { id } = Route.useParams();
  const { data: hive, error, isPending } = useHive(id);
  const [range, setRange] = useState<"24h" | "7d">("24h");
  const history = useHistory(id, range);
  const image = useLatestImage(id);
  const imageUrl = useImageUrl(image.data?.id);

  if (isPending || error) return <Loading error={error} />;
  if (!hive) {
    return (
      <main className="mx-auto max-w-xl p-6 text-center">
        <p className="text-lg">We couldn't find this hive.</p>
        <Link to="/" className="mt-4 inline-block rounded-xl bg-primary px-5 py-3 font-semibold">
          Back to hives
        </Link>
      </main>
    );
  }
  const offline = hive.status === "offline";
  const found = detections(image.data);

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-4 py-6 sm:px-6">
      <Link
        to="/"
        className="inline-flex min-h-12 items-center gap-2 rounded-xl px-2 font-semibold"
      >
        <ArrowLeft className="size-5" />
        Hives
      </Link>

      {offline && (
        <div
          role="alert"
          className="mt-3 flex items-start gap-3 rounded-2xl bg-offline p-4 text-primary-foreground"
        >
          <WifiOff className="mt-0.5 size-6 shrink-0" />
          <p>
            {hive.nodeId ? (
              <>
                <strong>This hive is offline.</strong> The data is from {hive.lastUpdate}. Check the
                device's power and signal.
              </>
            ) : (
              <>
                <strong>No node is attached to this hive.</strong> Assign one to start receiving
                data.
              </>
            )}
          </p>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{hive.name}</h1>
          <p className="text-muted-foreground">
            {hive.location} · Updated {hive.lastUpdate}
            {hive.nodeId && ` · ${hive.nodeId}`}
            {hive.simulated && " (simulated)"}
          </p>
        </div>
        <StatusBadge status={hive.status} />
      </div>

      <div className="mt-5 grid grid-cols-2 gap-4">
        <Big
          icon={<Thermometer className="size-5" />}
          label="Temperature"
          value={`${hive.temperature ?? "—"} °C`}
        />
        <Big
          icon={<Droplets className="size-5" />}
          label="Humidity"
          value={`${hive.humidity ?? "—"} %`}
        />
      </div>

      <div
        className="mt-6 inline-flex rounded-2xl bg-card p-1 ring-1 ring-border"
        role="group"
        aria-label="Period"
      >
        {(["24h", "7d"] as const).map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            aria-pressed={range === r}
            className={`min-h-12 rounded-xl px-5 font-semibold ${range === r ? "bg-primary" : "text-muted-foreground"}`}
          >
            {r === "24h" ? "24 h" : "7 days"}
          </button>
        ))}
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <ChartCard
          title="Temperature (°C)"
          data={history.data ?? []}
          dataKey="temperature"
          color="var(--warning)"
        />
        <ChartCard
          title="Humidity (%)"
          data={history.data ?? []}
          dataKey="humidity"
          color="var(--chart-blue)"
        />
      </div>
      {history.data?.length === 0 && (
        <p className="mt-2 text-muted-foreground">No readings in this period.</p>
      )}

      <section className="mt-6 rounded-2xl bg-card p-5 ring-1 ring-border">
        <h2 className="text-lg font-bold">Latest entrance image</h2>
        {image.data ? (
          <>
            <DetectionImage src={imageUrl} alt="Hive entrance with bees" detections={found} />
            <p className="mt-3 text-muted-foreground">
              {found.length
                ? `${found.length} possible pest${found.length === 1 ? "" : "s"} detected.`
                : "No pests detected in this image."}
            </p>
          </>
        ) : (
          <div className="mt-3 flex aspect-[16/10] flex-col items-center justify-center gap-2 rounded-xl bg-muted text-muted-foreground">
            <Camera className="size-10" />
            <p>{image.isPending ? "Loading…" : "The node has not sent any images yet."}</p>
          </div>
        )}
      </section>
    </main>
  );
}

function Big({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-card p-5 ring-1 ring-border">
      <p className="flex items-center gap-1.5 text-muted-foreground">
        {icon}
        {label}
      </p>
      <p className="mt-1 text-3xl font-bold">{value}</p>
    </div>
  );
}

function ChartCard({
  title,
  data,
  dataKey,
  color,
}: {
  title: string;
  data: object[];
  dataKey: string;
  color: string;
}) {
  return (
    <section className="rounded-2xl bg-card p-4 ring-1 ring-border">
      <h2 className="mb-2 font-bold">{title}</h2>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ left: -20, right: 8, top: 8 }}>
            <CartesianGrid stroke="var(--track)" vertical={false} />
            <XAxis dataKey="time" tick={{ fontSize: 12 }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 12 }} domain={["auto", "auto"]} />
            <Tooltip />
            <Line
              type="monotone"
              dataKey={dataKey}
              stroke={color}
              strokeWidth={3}
              dot={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
