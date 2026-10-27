import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ApiError, api, apiFetch, type ApiImage, type Page } from "@/lib/api";
import { useAccount } from "@/hooks/use-account";

export type Detection = {
  label: string;
  confidence: number;
  x: number;
  y: number;
  w: number;
  h: number;
};

const LABELS: Record<string, string> = {
  varroa: "Varroa mite",
  hornet: "Hornet",
  shb: "Small hive beetle",
  bee: "Bee",
};

/** Detected objects as percentages of the picture; boxes are [x1, y1, x2, y2] in pixels. Bees are left out. */
export function detections(image: ApiImage | null | undefined): Detection[] {
  if (!image?.width || !image.height) return [];
  const { width: W, height: H } = image;
  return image.objects
    .filter((o) => o.cls !== "bee")
    .map(({ cls, conf, box: [x1, y1, x2, y2] }) => ({
      label: LABELS[cls] ?? cls,
      confidence: Math.round(conf * 100),
      x: (x1 / W) * 100,
      y: (y1 / H) * 100,
      w: ((x2 - x1) / W) * 100,
      h: ((y2 - y1) / H) * 100,
    }));
}

const notFoundIsNull = (e: unknown) => {
  if (e instanceof ApiError && e.status === 404) return null;
  throw e;
};

export function useLatestImage(hiveId: string) {
  const { user } = useAccount();
  return useQuery({
    queryKey: ["images", hiveId, "latest"],
    enabled: !!user,
    queryFn: () => api<ApiImage>(`/api/v1/hives/${hiveId}/images/latest`).catch(notFoundIsNull),
  });
}

/** The hive's picture closest before the alert opened (same window the alert emails use). */
export function useAlertImage(hiveId: string | null, openedAt: string | undefined) {
  const { user } = useAccount();
  return useQuery({
    queryKey: ["images", hiveId, "at", openedAt],
    enabled: !!user && !!hiveId && !!openedAt,
    queryFn: async () => {
      const t = new Date(openedAt!).getTime();
      const from = new Date(t - 3_600_000).toISOString();
      const to = new Date(t + 300_000).toISOString();
      const page = await api<Page<ApiImage>>(
        `/api/v1/hives/${hiveId}/images?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&limit=1`,
      );
      return page.items[0] ?? null;
    },
  });
}

/** The JPEG needs the Authorization header, which an <img src> cannot send, so it is fetched as a blob. */
export function useImageUrl(imageId: string | undefined, width = 640): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!imageId) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    apiFetch(`/api/v1/images/${imageId}/file?w=${width}`)
      .then((r) => r.blob())
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => !cancelled && setUrl(null));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setUrl(null);
    };
  }, [imageId, width]);
  return url;
}
