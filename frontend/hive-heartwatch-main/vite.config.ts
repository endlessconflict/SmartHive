// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// The SmartHive API (Caddy in infra/docker-compose.yml). The browser only ever talks to this dev server,
// so the API needs no CORS and its SameSite=Strict refresh cookie works.
const API_URL = process.env["SMARTHIVE_API_URL"] ?? "http://localhost:8080";

export default defineConfig({
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
  vite: {
    server: {
      port: 5173, // Caddy already listens on 8080
      proxy: { "/api": { target: API_URL, ws: true } },
    },
  },
});
