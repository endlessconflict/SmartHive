import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Eye, EyeOff, LogIn, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAccount } from "@/hooks/use-account";
import { ApiError, login } from "@/lib/api";

export const Route = createFileRoute("/auth")({
  head: () => ({
    meta: [
      { title: "Iniciar sesión — Smart Hive" },
      { name: "description", content: "Acceda a Smart Hive con su correo y contraseña." },
      { property: "og:title", content: "Iniciar sesión — Smart Hive" },
      { property: "og:description", content: "Acceso a su cuenta de Smart Hive." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: AuthPage,
});

// The SmartHive API has no self sign-up or password reset: an administrator creates accounts
// (`smarthive create-user`) and sets passwords.
function AuthPage() {
  const account = useAccount();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email.trim(), password);
      await account.refresh();
      await navigate({ to: "/" });
    } catch (failure) {
      const status = failure instanceof ApiError ? failure.status : 0;
      setError(
        status === 401
          ? "El correo o la contraseña no son correctos."
          : status === 429
            ? "Demasiados intentos fallidos. Espere unos minutos e intente de nuevo."
            : "No se pudo conectar con el servidor. Revise que el backend esté encendido.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-md px-4 py-10 sm:py-14">
      <div className="mb-6 flex size-14 items-center justify-center rounded-2xl bg-muted text-foreground">
        <UserRound className="size-7" />
      </div>
      <h1 className="mb-7 text-3xl font-bold">{account.user ? "Su cuenta" : "Iniciar sesión"}</h1>
      {account.loading ? (
        <p role="status">Cargando…</p>
      ) : account.user ? (
        <>
          <p className="mb-1 text-xl font-semibold">{account.name}</p>
          <p className="mb-6 text-muted-foreground">{account.user.email}</p>
          <Button asChild className="min-h-12">
            <Link to="/">Ver colmenas</Link>
          </Button>
        </>
      ) : (
        <form onSubmit={submit} className="space-y-5">
          <div>
            <label htmlFor="email" className="mb-2 block font-semibold">
              Correo electrónico
            </label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="min-h-12 border-border bg-card text-base"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-2 block font-semibold">
              Contraseña
            </label>
            <div className="relative">
              <Input
                id="password"
                type={visible ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                className="min-h-12 border-border bg-card pr-14 text-base"
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="absolute right-0 top-0 size-12"
                aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
                title={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
                onClick={() => setVisible(!visible)}
              >
                {visible ? <EyeOff /> : <Eye />}
              </Button>
            </div>
          </div>
          {error && (
            <p role="alert" className="rounded-xl bg-danger-soft p-3 text-danger">
              {error}
            </p>
          )}
          <Button type="submit" disabled={busy} className="min-h-12 w-full text-base font-bold">
            <LogIn />
            {busy ? "Espere…" : "Entrar"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            Las cuentas las crea un administrador del sistema.
          </p>
        </form>
      )}
    </main>
  );
}
