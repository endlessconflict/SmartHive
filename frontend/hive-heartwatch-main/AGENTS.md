<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

- All data comes from the SmartHive API (backend/ in the SmartHive repository, docs/05-backend/06-api-design.md) through `src/lib/api.ts`; there is no Supabase and no demonstration data.
- The dev server proxies `/api` to the API (`vite.config.ts`, `SMARTHIVE_API_URL`, default http://localhost:8080), so requests stay same-origin: the API has no CORS and its refresh cookie is SameSite=Strict.
- Accounts are created by an administrator (`smarthive create-user`); the API has no sign-up or password reset. Monitoring pages need a signed-in user.
- Account state lives in the root: the access token in memory, the session restored from the refresh cookie on load. Names come from `/api/v1/me`.
- Live updates come from the `/api/v1/ws` WebSocket (`src/lib/live.ts`), which only marks React Query data stale.
