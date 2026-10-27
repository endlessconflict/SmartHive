import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ArrowLeft, Camera } from "lucide-react";
import {
  ALERT_STATUS_LABELS,
  ALERT_TYPE_LABELS,
  useAlert,
  useUpdateAlert,
  type AlertStatus,
} from "@/data/alerts";
import { useHives } from "@/data/hives";
import { detections, useAlertImage, useImageUrl } from "@/data/images";
import { AlertStatusBadge } from "@/components/AlertStatusBadge";
import { DetectionImage } from "@/components/DetectionImage";
import { Loading, RequireLogin } from "@/components/RequireLogin";
import { alertIcon } from "@/components/alert-icon";

export const Route = createFileRoute("/alertas/$id")({
  head: () => ({
    meta: [
      { title: "Alert detail — Smart Hive" },
      { name: "description", content: "Image, note and status of the alert." },
      { property: "og:title", content: "Alert detail — Smart Hive" },
      { property: "og:description", content: "Review and handle an alert from your hive." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: () => (
    <RequireLogin>
      <AlertDetail />
    </RequireLogin>
  ),
});

const statuses: AlertStatus[] = ["new", "in_progress", "resolved"];
const order = (s: AlertStatus) => statuses.indexOf(s);
const PEST_TYPES = new Set(["varroa", "beetle", "hornet"]);

function AlertDetail() {
  const { id } = Route.useParams();
  const { data: alert, error, isPending } = useAlert(id);
  const update = useUpdateAlert(id);
  const hive = useHives().data?.find((h) => h.id === alert?.hiveId);
  const image = useAlertImage(
    alert && PEST_TYPES.has(alert.type) ? alert.hiveId : null,
    alert?.openedAt,
  );
  const imageUrl = useImageUrl(image.data?.id);
  const [note, setNote] = useState("");
  useEffect(() => setNote(alert?.note ?? ""), [alert?.note]);

  if (isPending) return <Loading />;
  if (!alert) {
    return (
      <main className="mx-auto max-w-xl p-6 text-center">
        <p>
          {error ? `We couldn't load this alert: ${error.message}` : "We couldn't find this alert."}
        </p>
        <Link
          to="/alertas"
          className="mt-4 inline-block rounded-xl bg-primary px-5 py-3 font-semibold"
        >
          Back
        </Link>
      </main>
    );
  }
  const { Icon, cls } = alertIcon(alert.type);
  const resolved = alert.status === "resolved";

  return (
    <main className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <Link
        to="/alertas"
        className="inline-flex min-h-12 items-center gap-2 rounded-xl px-2 font-semibold"
      >
        <ArrowLeft className="size-5" />
        Alerts
      </Link>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{ALERT_TYPE_LABELS[alert.type]}</h1>
          <p className="text-muted-foreground">
            {hive ? (
              <Link to="/colmena/$id" params={{ id: hive.id }} className="font-semibold underline">
                {hive.name}
              </Link>
            ) : (
              alert.nodeId
            )}
            {alert.confidence !== null && ` · Confidence ${alert.confidence} %`} · {alert.date}
          </p>
          <p className="text-sm text-muted-foreground">
            {alert.title} · severity {alert.severity}
          </p>
        </div>
        <AlertStatusBadge status={alert.status} />
      </div>

      <section className="mt-5 overflow-hidden rounded-2xl bg-card ring-1 ring-border">
        {PEST_TYPES.has(alert.type) && image.data ? (
          <div className="px-5 pb-5">
            <DetectionImage
              src={imageUrl}
              alt="Hive entrance image"
              detections={detections(image.data)}
            />
          </div>
        ) : (
          <div className={`flex aspect-[16/10] flex-col items-center justify-center gap-2 ${cls}`}>
            {PEST_TYPES.has(alert.type) ? (
              <Camera className="size-12" />
            ) : (
              <Icon className="size-12" />
            )}
            <p className="px-4 text-center font-semibold">
              {alert.type === "offline"
                ? "No image: the node stopped sending data."
                : PEST_TYPES.has(alert.type)
                  ? image.isPending
                    ? "Loading image…"
                    : "No image from around the time of this alert."
                  : alert.title}
            </p>
          </div>
        )}
      </section>

      <section className="mt-5 rounded-2xl bg-card p-5 ring-1 ring-border">
        <h2 className="text-lg font-bold">Status</h2>
        <div className="mt-3 grid grid-cols-3 gap-2" role="group" aria-label="Change status">
          {statuses.map((s) => (
            <button
              key={s}
              aria-pressed={alert.status === s}
              // alerts only move forward: new → in progress → resolved
              disabled={update.isPending || order(s) <= order(alert.status)}
              onClick={() => update.mutate({ status: s, note })}
              className={`min-h-12 rounded-xl px-2 font-semibold ring-1 ring-border disabled:cursor-not-allowed ${alert.status === s ? "bg-primary" : "bg-muted text-muted-foreground disabled:opacity-50"}`}
            >
              {ALERT_STATUS_LABELS[s]}
            </button>
          ))}
        </div>
        {update.error && (
          <p role="alert" className="mt-2 text-danger">
            Could not change the status: {update.error.message}
          </p>
        )}

        <label htmlFor="note" className="mt-5 block text-lg font-bold">
          Resolution note
        </label>
        <textarea
          id="note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={4}
          disabled={resolved}
          maxLength={2000}
          placeholder="E.g.: I checked the hive and applied treatment."
          className="mt-2 w-full rounded-xl border-2 bg-background p-3 focus:border-primary focus:outline-none disabled:opacity-70"
        />
        {!resolved && (
          <button
            onClick={() => update.mutate({ status: "resolved", note })}
            disabled={update.isPending}
            className="mt-3 min-h-12 w-full rounded-xl bg-primary px-5 font-bold sm:w-auto"
          >
            Resolve with this note
          </button>
        )}
        {resolved && (
          <p className="mt-2 font-semibold text-success" role="status">
            Resolved{alert.note ? "; the note is saved." : "."}
          </p>
        )}
      </section>
    </main>
  );
}
