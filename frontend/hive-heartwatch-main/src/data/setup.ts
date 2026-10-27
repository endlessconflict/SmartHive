import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Apiary, type Page } from "@/lib/api";
import { useAccount } from "@/hooks/use-account";

export type ApiNode = {
  id: string;
  simulated: boolean;
  status: string;
  last_seen_at: string | null;
  registered_at: string;
  has_token: boolean;
  hive_id: string | null;
};

export type ApiaryIn = { name: string; lat: number | null; lon: number | null; timezone: string };
export type HiveIn = { name: string; hive_type: string | null; boxes: number | null };

export function useApiaries() {
  const { user } = useAccount();
  return useQuery({
    queryKey: ["apiaries"],
    enabled: !!user,
    queryFn: async () => (await api<Page<Apiary>>("/api/v1/apiaries?limit=200")).items,
  });
}

/** Administrators only: the API answers 403 to anyone else. */
export function useNodes() {
  const { user } = useAccount();
  return useQuery({
    queryKey: ["nodes"],
    enabled: user?.role === "admin",
    queryFn: () => api<ApiNode[]>("/api/v1/nodes"),
  });
}

/** A mutation that refreshes everything the dashboard shows about apiaries, hives and nodes. */
function useSetupMutation<T, R>(fn: (input: T) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of ["apiaries", "hives", "nodes"])
        void client.invalidateQueries({ queryKey: [key] });
    },
  });
}

const post = <R>(path: string, body?: unknown) =>
  api<R>(path, { method: "POST", ...(body === undefined ? {} : { body: JSON.stringify(body) }) });

export const useCreateApiary = () =>
  useSetupMutation((body: ApiaryIn) => post<Apiary>("/api/v1/apiaries", body));

export const useCreateHive = () =>
  useSetupMutation(({ apiaryId, ...body }: HiveIn & { apiaryId: string }) =>
    post<{ id: string }>(`/api/v1/apiaries/${apiaryId}/hives`, body),
  );

/** Creates the node, or issues a token to one that already spoke over MQTT. The token is shown once. */
export const useRegisterNode = () =>
  useSetupMutation((id: string) =>
    post<ApiNode & { device_token: string }>("/api/v1/nodes", { id }),
  );

export const useAssignNode = () =>
  useSetupMutation(({ nodeId, hiveId }: { nodeId: string; hiveId: string }) =>
    post<ApiNode>(`/api/v1/nodes/${nodeId}/assign`, { hive_id: hiveId }),
  );

export const useUnassignNode = () =>
  useSetupMutation((nodeId: string) => post<ApiNode>(`/api/v1/nodes/${nodeId}/unassign`));
