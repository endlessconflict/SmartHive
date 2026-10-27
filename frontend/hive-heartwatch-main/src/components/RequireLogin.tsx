import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useAccount } from "@/hooks/use-account";

/** Hive data comes from the API, which answers signed-in users only. */
export function RequireLogin({ children }: { children: ReactNode }) {
  const account = useAccount();
  if (account.loading)
    return (
      <main className="mx-auto max-w-xl p-6 text-center">
        <p role="status">Cargando…</p>
      </main>
    );
  if (!account.user) {
    return (
      <main className="mx-auto max-w-xl p-6 text-center">
        <p className="text-lg">Inicie sesión para ver sus colmenas.</p>
        <Link
          to="/auth"
          className="mt-4 inline-block rounded-xl bg-primary px-5 py-3 font-semibold"
        >
          Iniciar sesión
        </Link>
      </main>
    );
  }
  return <>{children}</>;
}

export function Loading({ error, text = "Loading…" }: { error?: Error | null; text?: string }) {
  return (
    <main className="mx-auto max-w-xl p-6 text-center">
      {error ? (
        <p role="alert" className="text-danger">
          Could not load the data: {error.message}
        </p>
      ) : (
        <p role="status">{text}</p>
      )}
    </main>
  );
}
