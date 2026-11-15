import { Link } from "@tanstack/react-router";
import { format } from "date-fns";
import { Camera, ChevronRight } from "lucide-react";
import type { ApiAlert, ApiImage } from "@/lib/api";
import { PICTURE_ALERTS, pictureAlerts } from "@/data/alert-pictures";
import { detections, useImageUrl, useLatestImage } from "@/data/images";
import { useActiveAlerts } from "@/data/hives";
import { DetectionImage } from "@/components/DetectionImage";

function Picture({ image, alt }: { image: ApiImage; alt: string }) {
  const url = useImageUrl(image.id);
  const found = detections(image);
  return (
    <>
      <DetectionImage src={url} alt={alt} detections={found} />
      <p className="mt-3 text-muted-foreground">
        {found.length
          ? `${found.length} possible pest${found.length === 1 ? "" : "s"} detected.`
          : "No pests detected in this image."}{" "}
        <span className="text-sm">
          Taken {format(new Date(image.captured_at), "d MMM, HH:mm")}.
        </span>
      </p>
    </>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <div className="mt-3 flex aspect-[16/10] flex-col items-center justify-center gap-2 rounded-xl bg-muted text-muted-foreground">
      <Camera className="size-10" />
      <p>{text}</p>
    </div>
  );
}

function AlertPicture({ hiveId, alert }: { hiveId: string; alert: ApiAlert }) {
  const { reason, title } = PICTURE_ALERTS[alert.rule_id] ?? { reason: "threat", title: "Alert" };
  const image = useLatestImage(hiveId, reason);
  return (
    <div className="rounded-xl ring-2 ring-danger/60 p-4">
      <Link
        to="/alertas/$id"
        params={{ id: alert.id }}
        className="flex min-h-12 items-center justify-between gap-2 font-bold text-danger"
      >
        {title}: {alert.title}
        <ChevronRight className="size-5 shrink-0" />
      </Link>
      {image.data ? (
        <Picture image={image.data} alt={`${title}: entrance picture`} />
      ) : (
        <Empty
          text={image.isPending ? "Loading…" : "The picture of this alert has not arrived yet."}
        />
      )}
    </div>
  );
}

export function HiveImage({ hiveId }: { hiveId: string }) {
  const alerts = useActiveAlerts();
  const withPicture = pictureAlerts(alerts.data ?? [], hiveId);
  const latest = useLatestImage(hiveId, undefined, !alerts.isPending && withPicture.length === 0);

  if (withPicture.length) {
    return (
      <>
        <h2 className="text-lg font-bold">Alert images</h2>
        <div className="mt-3 space-y-4">
          {withPicture.map((a) => (
            <AlertPicture key={a.id} hiveId={hiveId} alert={a} />
          ))}
        </div>
      </>
    );
  }
  return (
    <>
      <h2 className="text-lg font-bold">Latest entrance image</h2>
      {latest.data ? (
        <Picture image={latest.data} alt="Hive entrance with bees" />
      ) : (
        <Empty
          text={
            alerts.isPending || latest.isPending
              ? "Loading…"
              : "The node has not sent any images yet."
          }
        />
      )}
    </>
  );
}
