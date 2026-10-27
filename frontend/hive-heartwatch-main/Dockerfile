# SmartHive dashboard: TanStack Start built as a Node server (Nitro "node-server" preset).
# Lovable's build defaults to Cloudflare; NITRO_PRESET overrides it outside the Lovable sandbox.
# Served behind Caddy (infra/caddy/Caddyfile), which sends /api and /device to the backend,
# so the browser sees one origin, as the dev server's proxy does.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN NITRO_PRESET=node-server npm run build

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000
# the build bundles its runtime dependencies into .output, so no node_modules here
COPY --from=build --chown=node:node /app/.output ./.output
USER node
EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]
