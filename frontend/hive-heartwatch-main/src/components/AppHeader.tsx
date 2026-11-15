import { Link, useNavigate } from "@tanstack/react-router";
import { Bell, Inbox, LogOut, Settings } from "lucide-react";
import { useActiveAlerts } from "@/data/hives";
import { useInbox } from "@/data/notifications";
import { useAccount } from "@/hooks/use-account";
import { Button } from "@/components/ui/button";
import { logout } from "@/lib/api";
import { useState } from "react";

export function AppHeader() {
  const unread = (useActiveAlerts().data ?? []).filter((a) => a.state === "open").length;
  const unreadMessages = useInbox().data?.unread ?? 0;
  const account = useAccount();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function signOut() {
    setBusy(true);
    setError("");
    try {
      await logout();
      await navigate({ to: "/auth", replace: true });
    } catch {
      setError("No se pudo cerrar sesión. Intente de nuevo.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <header className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 pt-5 sm:px-6">
      <Link to="/" className="flex min-h-12 items-center gap-3">
        <span
          className="grid size-12 place-items-center rounded-2xl bg-primary text-2xl"
          aria-hidden="true"
        >
          🐝
        </span>
        <span className="text-xl font-bold">Smart Hive</span>
      </Link>
      <div className="ml-auto flex min-w-0 items-center gap-2 sm:gap-4">
        {!account.loading &&
          (account.user ? (
            <>
              <span className="max-w-32 break-words text-right font-semibold sm:max-w-64">
                {account.name}
              </span>
              <Button asChild variant="ghost" size="icon" className="size-12 shrink-0">
                <Link
                  to="/gestion"
                  aria-label="Configurar apiarios, colmenas y nodos"
                  title="Setup"
                >
                  <Settings />
                </Link>
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="size-12 shrink-0"
                aria-label="Cerrar sesión"
                title="Cerrar sesión"
                disabled={busy}
                onClick={signOut}
              >
                <LogOut />
              </Button>
            </>
          ) : (
            <Button asChild variant="ghost" className="min-h-12">
              <Link to="/auth">Iniciar sesión</Link>
            </Button>
          ))}
        <Link
          to="/notificaciones"
          aria-label={`Bandeja de notificaciones, ${unreadMessages} sin leer`}
          title="Inbox"
          className="relative grid size-12 place-items-center rounded-2xl bg-card ring-1 ring-border"
        >
          <Inbox className="size-6" />
          {unreadMessages > 0 && (
            <span className="absolute -right-1 -top-1 grid min-w-6 place-items-center rounded-full bg-danger px-1.5 text-xs font-bold text-primary-foreground">
              {unreadMessages}
            </span>
          )}
        </Link>
        <Link
          to="/alertas"
          aria-label={`Alertas, ${unread} nuevas`}
          className="relative grid size-12 place-items-center rounded-2xl bg-card ring-1 ring-border"
        >
          <Bell className="size-6" />
          {unread > 0 && (
            <span className="absolute -right-1 -top-1 grid min-w-6 place-items-center rounded-full bg-danger px-1.5 text-xs font-bold text-primary-foreground">
              {unread}
            </span>
          )}
        </Link>
      </div>
      {error && (
        <p role="alert" className="w-full text-right text-sm text-danger">
          {error}
        </p>
      )}
    </header>
  );
}
