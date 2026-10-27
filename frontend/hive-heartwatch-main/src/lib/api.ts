/**
 * SmartHive API client (docs/05-backend/06-api-design.md). Same origin: the dev server proxies /api.
 *
 * The access token lives in memory only. The refresh token is an HttpOnly cookie the browser sends to
 * /api/v1/auth/*, so a page reload signs back in through `restoreSession()`.
 */

export type Me = {
  id: string;
  email: string;
  display_name: string;
  role: "beekeeper" | "admin";
  notify_email: boolean;
  ntfy_topic: string | null;
};

export type Latest = { value: number | null; ts: string; clock_synced: boolean };

export type ApiHive = {
  id: string;
  apiary_id: string;
  name: string;
  hive_type: string | null;
  boxes: number | null;
  notes: string | null;
  archived: boolean;
  node_id: string | null;
  node_status: string | null;
  simulated: boolean;
  open_alerts: number;
  latest: Record<string, Latest>;
};

export type Apiary = {
  id: string;
  owner_id: string;
  name: string;
  lat: number | null;
  lon: number | null;
  timezone: string;
};

export type Point = {
  ts: string;
  value: number | null;
  min: number | null;
  max: number | null;
  n: number;
};
export type Series = {
  hive_id: string;
  quantity: string;
  bucket: string;
  points: Point[];
  truncated: boolean;
};

export type ApiAlert = {
  id: string;
  hive_id: string | null;
  node_id: string | null;
  rule_id: string;
  severity: "info" | "warning" | "critical";
  state: "open" | "acknowledged" | "resolved";
  title: string;
  details: Record<string, unknown>;
  opened_at: string;
  last_seen_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
};

export type ApiAlertDetail = ApiAlert & {
  events: { at: string; kind: string; actor: string | null; data: Record<string, unknown> }[];
};

export type DetectedObject = { cls: string; conf: number; box: [number, number, number, number] };

export type ApiImage = {
  id: string;
  node_id: string;
  hive_id: string | null;
  captured_at: string;
  reason: string;
  width: number | null;
  height: number | null;
  objects: DetectedObject[];
};

export type Page<T> = { items: T[]; next_cursor: string | null };

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
const signedOutListeners = new Set<() => void>();

export const getAccessToken = () => accessToken;

/** Called when the session cannot be renewed, so the app can show the login page. */
export function onSignedOut(listener: () => void) {
  signedOutListeners.add(listener);
  return () => void signedOutListeners.delete(listener);
}

async function problem(res: Response): Promise<ApiError> {
  let title = res.statusText;
  try {
    const body = await res.json();
    title = body.detail || body.title || title;
  } catch {
    // not JSON
  }
  return new ApiError(res.status, title);
}

async function tokens(path: string, init: RequestInit): Promise<boolean> {
  const res = await fetch(`/api/v1/auth/${path}`, {
    ...init,
    method: "POST",
    credentials: "same-origin",
  });
  if (!res.ok) {
    accessToken = null;
    if (path === "login") throw await problem(res);
    return false;
  }
  accessToken = (await res.json()).access_token;
  return true;
}

/** Trades the refresh cookie for a new access token; concurrent callers share one request. */
export function restoreSession(): Promise<boolean> {
  refreshing ??= tokens("refresh", {}).finally(() => (refreshing = null));
  return refreshing;
}

export async function login(email: string, password: string): Promise<void> {
  await tokens("login", {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export async function logout(): Promise<void> {
  accessToken = null;
  await fetch("/api/v1/auth/logout", { method: "POST", credentials: "same-origin" });
  signedOutListeners.forEach((l) => l());
}

/** Authenticated request. An expired access token is renewed once and the request repeated. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const send = () =>
    fetch(path, {
      ...init,
      headers: {
        ...init.headers,
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
    });
  let res = await send();
  if (res.status === 401 && (await restoreSession())) res = await send();
  if (res.status === 401) signedOutListeners.forEach((l) => l());
  if (!res.ok) throw await problem(res);
  return res;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const body =
    init.body === undefined
      ? init
      : { ...init, headers: { "Content-Type": "application/json", ...init.headers } };
  return (await apiFetch(path, body)).json();
}
