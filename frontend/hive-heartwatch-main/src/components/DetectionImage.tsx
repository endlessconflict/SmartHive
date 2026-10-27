import type { Detection } from "@/data/images";

/** An entrance picture with a red box and label per detected pest. */
export function DetectionImage({
  src,
  alt,
  detections,
}: {
  src: string | null;
  alt: string;
  detections: Detection[];
}) {
  return (
    <div className="relative mt-3 overflow-hidden rounded-xl">
      {/* natural aspect ratio, not object-cover: cropping would shift the boxes off the pests */}
      {src ? (
        <img src={src} alt={alt} className="h-auto w-full" />
      ) : (
        <div className="aspect-[16/10] w-full animate-pulse bg-muted" />
      )}
      {src &&
        detections.map((d, i) => (
          <div
            key={i}
            className="absolute rounded-md border-[3px] border-danger"
            style={{ left: `${d.x}%`, top: `${d.y}%`, width: `${d.w}%`, height: `${d.h}%` }}
          >
            <span className="absolute -top-7 left-0 whitespace-nowrap rounded bg-danger px-2 py-0.5 text-xs font-bold text-primary-foreground">
              {d.label} {d.confidence} %
            </span>
          </div>
        ))}
    </div>
  );
}
