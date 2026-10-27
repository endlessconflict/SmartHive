import { createFileRoute, Link } from "@tanstack/react-router";
import { useState, type FormEvent, type ReactNode } from "react";
import { formatDistanceToNow } from "date-fns";
import { Copy, Cpu, Hexagon, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loading, RequireLogin } from "@/components/RequireLogin";
import { useAccount } from "@/hooks/use-account";
import { useHives } from "@/data/hives";
import {
  useApiaries,
  useAssignNode,
  useCreateApiary,
  useCreateHive,
  useNodes,
  useRegisterNode,
  useUnassignNode,
  type ApiNode,
} from "@/data/setup";

export const Route = createFileRoute("/gestion")({
  head: () => ({
    meta: [
      { title: "Setup — Smart Hive" },
      { name: "description", content: "Create apiaries and hives, and attach nodes to them." },
    ],
  }),
  component: () => (
    <RequireLogin>
      <SetupPage />
    </RequireLogin>
  ),
});

const field = "min-h-12 border-border bg-card text-base";
const select = `w-full rounded-md border px-3 ${field}`;

function SetupPage() {
  const { user } = useAccount();
  return (
    <main className="mx-auto max-w-4xl space-y-6 px-4 py-6 sm:px-6">
      <div>
        <h1 className="text-2xl font-bold">Setup</h1>
        <p className="text-muted-foreground">
          The order that works: an apiary, then its hives, then a node attached to each hive.
        </p>
      </div>
      <ApiariesSection />
      <HivesSection />
      {user?.role === "admin" ? (
        <NodesSection />
      ) : (
        <Section icon={<Cpu />} title="Nodes">
          <p className="text-muted-foreground">
            Only an administrator can register and attach nodes.
          </p>
        </Section>
      )}
    </main>
  );
}

function Section({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl bg-card p-5 ring-1 ring-border">
      <h2 className="mb-4 flex items-center gap-2 text-lg font-bold [&_svg]:size-5">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

function Label({ htmlFor, children }: { htmlFor: string; children: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1 block font-semibold">
      {children}
    </label>
  );
}

function Feedback({ error, ok }: { error: Error | null; ok?: string | false }) {
  if (error) {
    return (
      <p role="alert" className="rounded-xl bg-danger-soft p-3 text-danger">
        {error.message}
      </p>
    );
  }
  return ok ? (
    <p role="status" className="rounded-xl bg-success-soft p-3">
      {ok}
    </p>
  ) : null;
}

const optionalNumber = (v: string) => (v.trim() === "" ? null : Number(v));

function ApiariesSection() {
  const apiaries = useApiaries();
  const create = useCreateApiary();
  const [name, setName] = useState("");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [timezone, setTimezone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone);

  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate(
      { name: name.trim(), lat: optionalNumber(lat), lon: optionalNumber(lon), timezone },
      {
        onSuccess: () => {
          setName("");
          setLat("");
          setLon("");
        },
      },
    );
  }

  return (
    <Section icon={<MapPin />} title="Apiaries">
      {apiaries.data?.length ? (
        <ul className="mb-5 divide-y rounded-xl ring-1 ring-border">
          {apiaries.data.map((a) => (
            <li key={a.id} className="flex flex-wrap justify-between gap-2 p-3">
              <span className="font-semibold">{a.name}</span>
              <span className="text-sm text-muted-foreground">
                {a.lat !== null && a.lon !== null ? `${a.lat}, ${a.lon} · ` : ""}
                {a.timezone}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mb-5 text-muted-foreground">
          {apiaries.isPending ? "Loading…" : "No apiaries yet."}
        </p>
      )}
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Label htmlFor="apiary-name">New apiary</Label>
          <Input
            id="apiary-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={200}
            placeholder="e.g. Finca La Esperanza"
            className={field}
          />
        </div>
        <div>
          <Label htmlFor="apiary-lat">Latitude (optional)</Label>
          <Input
            id="apiary-lat"
            type="number"
            step="any"
            min={-90}
            max={90}
            value={lat}
            onChange={(e) => setLat(e.target.value)}
            placeholder="6.2442"
            className={field}
          />
        </div>
        <div>
          <Label htmlFor="apiary-lon">Longitude (optional)</Label>
          <Input
            id="apiary-lon"
            type="number"
            step="any"
            min={-180}
            max={180}
            value={lon}
            onChange={(e) => setLon(e.target.value)}
            placeholder="-75.5812"
            className={field}
          />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="apiary-tz">Time zone</Label>
          <Input
            id="apiary-tz"
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            required
            maxLength={64}
            className={field}
          />
          <p className="mt-1 text-sm text-muted-foreground">
            With latitude and longitude the server also downloads the local weather once a day.
          </p>
        </div>
        <div className="space-y-3 sm:col-span-2">
          <Feedback
            error={create.error}
            ok={create.isSuccess && `Apiary "${create.data.name}" created.`}
          />
          <Button type="submit" disabled={create.isPending} className="min-h-12 font-bold">
            {create.isPending ? "Saving…" : "Create apiary"}
          </Button>
        </div>
      </form>
    </Section>
  );
}

function HivesSection() {
  const apiaries = useApiaries();
  const hives = useHives();
  const create = useCreateHive();
  const [apiaryId, setApiaryId] = useState("");
  const [name, setName] = useState("");
  const [hiveType, setHiveType] = useState("");
  const [boxes, setBoxes] = useState("");
  const chosen = apiaryId || apiaries.data?.[0]?.id || "";

  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate(
      {
        apiaryId: chosen,
        name: name.trim(),
        hive_type: hiveType.trim() || null,
        boxes: optionalNumber(boxes),
      },
      {
        onSuccess: () => {
          setName("");
          setHiveType("");
          setBoxes("");
        },
      },
    );
  }

  if (!apiaries.data?.length) {
    return (
      <Section icon={<Hexagon />} title="Hives">
        <p className="text-muted-foreground">Create an apiary first; every hive belongs to one.</p>
      </Section>
    );
  }
  return (
    <Section icon={<Hexagon />} title="Hives">
      {hives.data?.length ? (
        <ul className="mb-5 divide-y rounded-xl ring-1 ring-border">
          {hives.data.map((h) => (
            <li key={h.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
              <Link to="/colmena/$id" params={{ id: h.id }} className="font-semibold underline">
                {h.name}
              </Link>
              <span className="text-sm text-muted-foreground">
                {h.location} · {h.nodeId ? `node ${h.nodeId}` : "no node"}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mb-5 text-muted-foreground">
          {hives.isPending ? "Loading…" : "No hives yet."}
        </p>
      )}
      <form onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="hive-apiary">Apiary</Label>
          <select
            id="hive-apiary"
            value={chosen}
            onChange={(e) => setApiaryId(e.target.value)}
            className={select}
          >
            {apiaries.data.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label htmlFor="hive-name">New hive</Label>
          <Input
            id="hive-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={200}
            placeholder="e.g. Hive 1"
            className={field}
          />
        </div>
        <div>
          <Label htmlFor="hive-type">Type (optional)</Label>
          <Input
            id="hive-type"
            value={hiveType}
            onChange={(e) => setHiveType(e.target.value)}
            maxLength={64}
            placeholder="langstroth"
            className={field}
          />
        </div>
        <div>
          <Label htmlFor="hive-boxes">Boxes (optional)</Label>
          <Input
            id="hive-boxes"
            type="number"
            min={1}
            max={20}
            value={boxes}
            onChange={(e) => setBoxes(e.target.value)}
            className={field}
          />
        </div>
        <div className="space-y-3 sm:col-span-2">
          <Feedback
            error={create.error}
            ok={create.isSuccess && "Hive created. Attach a node to it below."}
          />
          <Button type="submit" disabled={create.isPending} className="min-h-12 font-bold">
            {create.isPending ? "Saving…" : "Create hive"}
          </Button>
        </div>
      </form>
    </Section>
  );
}

function NodesSection() {
  const nodes = useNodes();
  const register = useRegisterNode();
  const [id, setId] = useState("");
  const [copied, setCopied] = useState(false);

  function submit(e: FormEvent) {
    e.preventDefault();
    setCopied(false);
    register.mutate(id.trim(), { onSuccess: () => setId("") });
  }

  if (!nodes.data) return nodes.error ? <Loading error={nodes.error} /> : null;
  return (
    <Section icon={<Cpu />} title="Nodes">
      <p className="mb-4 text-muted-foreground">
        A node appears here by itself the first time it sends data over MQTT. Attach it to a hive so
        its readings show on the dashboard.
      </p>
      {nodes.data.length ? (
        <ul className="mb-6 space-y-3">
          {nodes.data.map((n) => (
            <NodeRow key={n.id} node={n} />
          ))}
        </ul>
      ) : (
        <p className="mb-6 text-muted-foreground">No nodes yet.</p>
      )}

      <form onSubmit={submit} className="space-y-3 border-t pt-5">
        <div>
          <Label htmlFor="node-id">Register a node</Label>
          <Input
            id="node-id"
            value={id}
            onChange={(e) => setId(e.target.value.toLowerCase())}
            required
            pattern="[a-z0-9][a-z0-9\-]{1,62}"
            placeholder="node-0002 or sim-0002"
            className={field}
          />
          <p className="mt-1 text-sm text-muted-foreground">
            Lowercase letters, digits and dashes. Ids starting with <code>sim-</code> are marked as
            simulated. Registering issues the device token for image uploads; MQTT also needs a
            certificate with the same id (<code>infra/pki/gen_certs.sh {id || "<id>"}</code>).
          </p>
        </div>
        <Feedback error={register.error} />
        {register.data && (
          <div role="status" className="space-y-2 rounded-xl bg-warning-soft p-4">
            <p className="font-semibold">
              Device token for {register.data.id}. Copy it now: it is not shown again.
            </p>
            <code className="block break-all rounded bg-card p-2 text-sm">
              {register.data.device_token}
            </code>
            <Button
              type="button"
              variant="outline"
              onClick={() =>
                void navigator.clipboard
                  .writeText(register.data.device_token)
                  .then(() => setCopied(true))
              }
            >
              <Copy />
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
        )}
        <Button type="submit" disabled={register.isPending} className="min-h-12 font-bold">
          {register.isPending ? "Saving…" : "Register node"}
        </Button>
      </form>
    </Section>
  );
}

function NodeRow({ node }: { node: ApiNode }) {
  const hives = useHives().data ?? [];
  const assign = useAssignNode();
  const unassign = useUnassignNode();
  const [hiveId, setHiveId] = useState("");
  const chosen = hiveId || hives[0]?.id || "";
  const current = hives.find((h) => h.id === node.hive_id);
  const error = assign.error ?? unassign.error;

  return (
    <li className="rounded-xl p-4 ring-1 ring-border">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-bold">
          {node.id}
          {node.simulated && (
            <span className="ml-2 text-sm font-normal text-muted-foreground">simulated</span>
          )}
        </p>
        <p className="text-sm text-muted-foreground">
          {node.status}
          {node.last_seen_at &&
            ` · seen ${formatDistanceToNow(new Date(node.last_seen_at), { addSuffix: true })}`}
          {node.has_token && " · has device token"}
        </p>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {node.hive_id ? (
          <>
            <span>
              Attached to <strong>{current?.name ?? node.hive_id}</strong>
            </span>
            <Button
              variant="outline"
              disabled={unassign.isPending}
              onClick={() => unassign.mutate(node.id)}
            >
              Detach
            </Button>
          </>
        ) : hives.length ? (
          <>
            <select
              aria-label={`Hive for ${node.id}`}
              value={chosen}
              onChange={(e) => setHiveId(e.target.value)}
              className={`${select} sm:w-auto`}
            >
              {hives.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name} ({h.location}){h.nodeId ? ` · has ${h.nodeId}` : ""}
                </option>
              ))}
            </select>
            <Button
              disabled={assign.isPending}
              onClick={() => assign.mutate({ nodeId: node.id, hiveId: chosen })}
            >
              Attach
            </Button>
          </>
        ) : (
          <span className="text-muted-foreground">Create a hive to attach this node.</span>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-2 text-danger">
          {error.message}
        </p>
      )}
    </li>
  );
}
