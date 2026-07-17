# @moneymatch/api-client

Typed TypeScript client generated from the FastAPI OpenAPI schema
(00-README §2 "Type sharing"). **Never hand-write API types in `apps/web`** —
regenerate this instead.

## Regenerate

The build uses the committed `src/generated/schema.ts`. To refresh it after an
API change:

```bash
# From a running API (pulls a fresh schema, then regenerates types):
make api            # or: uvicorn moneymatch_api.main:app --port 8000
pnpm gen:api        # curls /openapi.json → openapi.json, runs openapi-typescript

# Or regenerate types from the committed openapi.json snapshot (offline):
pnpm --filter @moneymatch/api-client gen
```

Commit both `openapi.json` and `src/generated/schema.ts`.

## Use

```ts
import { createApiClient } from '@moneymatch/api-client';

const api = createApiClient({
  baseUrl: import.meta.env.VITE_API_BASE_URL,
  getToken: () =>
    supabase.auth.getSession().then((s) => s.data.session?.access_token ?? null),
});

const { data, error } = await api.GET('/api/v1/me');
```
