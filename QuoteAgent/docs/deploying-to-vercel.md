# Deploying QuoteAgent to Vercel

Written for: whoever puts the demonstration on a URL the product owner can
open.

**One Vercel project, one URL, nothing to set up.** No database to create and
no environment variables to fill in. The interface and the API deploy together
from this folder and share one address.

---

## Deploy it (zero setup)

1. In Vercel: **Add New… → Project**, import the `engrhasnain/Demos` repository.
2. **Root Directory:** `QuoteAgent`. Leave everything else as it is.
3. Press **Deploy**.

When it is live, open the URL and sign in as
`admin@hengtai-industrial.example` with `demo1234`. The data is already
there: the first request after a start fills the database with the
demonstration data, so there is no "load the data" step.

Sending somebody a link of the form
`https://your-project.vercel.app/sign-in?as=paul.lee@hengtai-industrial.example`
opens the demonstration directly in that role.

**Check it:** `https://your-project.vercel.app/api/health` should answer
`"status": "ready"`.

---

## How it works

`QuoteAgent/vercel.json` uses Vercel **services**:

```json
{
  "services": {
    "frontend": { "root": "frontend/" },
    "backend": { "root": "backend/", "entrypoint": "api/index.py" }
  },
  "rewrites": [
    { "source": "/api/(.*)", "destination": { "service": "backend" } },
    { "source": "/(.*)", "destination": { "service": "frontend" } }
  ]
}
```

- **Same origin.** Every backend route already starts with `/api/`, so
  `/api/*` goes to the FastAPI service and everything else to the Next.js
  interface. `frontend/.env.production` sets `NEXT_PUBLIC_API_URL` to empty, so
  the production interface calls `/api/...` on its own address: no CORS, no
  backend address to configure. `npm run dev` still talks to
  `http://127.0.0.1:8000`.
- **Data with no database.** On Vercel the backend uses a SQLite file in
  `/tmp`. On the first request after a start it creates the tables and, if the
  database is empty, generates the demonstration data: 1,000 parts, 80
  customers, the sales team and two dozen worked requests in every state. It is
  generated rather than copied, so every date is relative to today. It takes
  about ten seconds, once per server; requests that arrive meanwhile wait for
  it.
- **Temporary, and it says so.** Changes last as long as that server does.
  When Vercel starts a new one, it starts again from fresh demonstration data.
  A thin bar across the top says *Demonstration data — resets when the server
  restarts.*

## Optional settings

None of these are needed for a demonstration.

| Name | What it does |
|---|---|
| `JWT_SECRET` | Signs sign-in tokens. Optional for a demonstration (the published default is used and a warning is logged); set a long random string for anything else. |
| `DATABASE_URL` | Keeps the data. See the upgrade below. |
| `AUTO_LOAD_DEMO_DATA` | `false` stops the automatic load. `true` turns it on anywhere, including locally or on PostgreSQL (it only ever fills an empty database). |
| `AUTO_LOAD_PRODUCT_TARGET`, `AUTO_LOAD_CUSTOMER_TARGET` | Size of the automatic load. Defaults 1000 and 80. Larger means a slower first request. |
| `MODEL_API_KEY`, `MODEL_BASE_URL` | A hosted model for the reading step. Without them the built-in engine does it and everything still works. |

Environment variables are read when the backend starts, so redeploy after
changing one.

## Optional upgrade: PostgreSQL, so the data persists

1. Create a PostgreSQL database (Neon or Vercel Postgres take about a minute).
2. In the project's **Settings → Environment Variables**, add `DATABASE_URL`.
   Write the scheme as `postgresql+psycopg://user:password@host/database`; a
   plain `postgres://` string will not work, so change the scheme and keep the
   rest.
3. Add `JWT_SECRET` as well, then redeploy.
4. Open the site and press **Load the demonstration data** (choose **A smaller
   set**), or set `AUTO_LOAD_DEMO_DATA=true` to have the first request do it.

`/api/health` then reports `"database": "PostgreSQL"` and the bar at the top
disappears.

---

## What changes when it runs on Vercel, and why

| | A long running server | Vercel |
|---|---|---|
| Database | SQLite file, no setup | SQLite in `/tmp`, filled on start; or PostgreSQL |
| Loading the data | A button and a background load with a progress bar | Automatic on the first request; the button loads inside the request |
| Catalogue size | 18,000 parts | 1,000 automatically, 2,000 with the button's smaller set |
| Documents | Written under `backend/var` | Written to `/tmp`, regenerated on demand |
| Database connections | Pooled and recycled | One per invocation, returned immediately |

**Why a smaller catalogue.** The matcher holds a search index in the function's
memory and rebuilds it on every cold start. A thousand parts builds in about a
second and every page stays quick. Run the full
catalogue locally, or on any host that keeps a process alive.

**Cold starts.** The first request after an idle period pays for the Python
runtime, the import and the data load: expect ten to fifteen seconds once,
then normal speed. A demonstration that matters is worth opening once
beforehand.

---

## If something is wrong

**The first page sits on loading for a while** — that is the first request
filling the database. It happens once per server.

**"The backend did not answer"** — the backend service failed to start. Open
the deployment's logs in Vercel and look at the backend function.

**Changes disappeared** — the server restarted and started again from fresh
demonstration data. Use the PostgreSQL upgrade to keep them.

**`ModuleNotFoundError: psycopg`** — the driver is in
`backend/requirements.txt`, so this means the Root Directory is not
`QuoteAgent`.
