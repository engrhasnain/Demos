# Deploying OpsAgent to Vercel

Written for: whoever puts the demonstration on a URL the product owner can
open.

**One Vercel project, one URL, nothing to set up.** No database to create and
no environment variables to fill in. The interface and the API deploy together
from this folder and share one address.

---

## Deploy it (zero setup)

1. In Vercel: **Add New… → Project**, import the repository.
2. **Root Directory:** `OpsAgent`. Leave everything else as it is.
3. Press **Deploy**.

When it is live, open the URL and sign in as
`admin@hengtai-industrial.example` with `demo1234` — or any of the other
accounts listed on the overview page. The data is already there: the first
request after a start fills the database with the demonstration data and asks
a handful of questions as different people, so there is no "build the
business" step and no screen opens empty.

**Check it:** `https://your-project.vercel.app/api/health` should answer
`"status": "ok"`.

---

## How it works

`OpsAgent/vercel.json` uses Vercel **services**:

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
  interface. `frontend/.env.production` sets `NEXT_PUBLIC_API_URL` to empty,
  so the production interface calls `/api/...` on its own address: no CORS, no
  backend address to configure. `npm run dev` still talks to
  `http://127.0.0.1:8005`.
- **Data with no database.** On Vercel the backend uses a SQLite file in
  `/tmp`. On the first request after a start it creates the tables and, if the
  database is empty, generates the demonstration data — customers, suppliers,
  the part catalogue, orders, invoices, documents and the six demonstration
  accounts — and then asks a small set of real questions through the same
  engine every other question goes through: an ordinary answer, a
  whole-company figure open to a director, the same figure refused to a
  salesperson, a proposal raised for somebody to decide, and the planted
  supplier email read alongside a question so the "a fooled planner reaches
  nothing extra" claim has something on screen to point at. It is generated
  rather than copied, so every date is relative to today. Requests that arrive
  while it runs wait for it.
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
| `AUTO_LOAD_CUSTOMER_TARGET`, `AUTO_LOAD_ORDER_TARGET` | Size of the automatic load. Defaults 60 and 280. Larger means a slower first request. |
| `MODEL_API_KEY`, `MODEL_BASE_URL` | A hosted model for the writing step. Without them the built-in engine does it and everything still works. |

Environment variables are read when the backend starts, so redeploy after
changing one.

## Optional upgrade: PostgreSQL, so the data persists

1. Create a PostgreSQL database (Neon or Vercel Postgres take about a minute).
2. In the project's **Settings → Environment Variables**, add `DATABASE_URL`.
   Write the scheme as `postgresql+psycopg://user:password@host/database`; a
   plain `postgres://` string will not work, so change the scheme and keep the
   rest.
3. Add `JWT_SECRET` as well, then redeploy.
4. Open the site and sign in as the administrator, then press **Build the
   business** on the overview page, or set `AUTO_LOAD_DEMO_DATA=true` to have
   the first request do it.

---

## What changes when it runs on Vercel, and why

| | A long running server | Vercel |
|---|---|---|
| Database | SQLite file, no setup | SQLite in `/tmp`, filled on start; or PostgreSQL |
| Loading the data | The overview page's "Build the business" button | Automatic on the first request |
| Business size | 200 customers, 1,200 orders | 60 customers, 280 orders, automatically |
| Database connections | Pooled and recycled | One per invocation, returned immediately |

**Cold starts.** The first request after an idle period pays for the Python
runtime, the import, the data generation and the seeded questions: expect a
few seconds once, then normal speed. A demonstration that matters is worth
opening once beforehand.

---

## If something is wrong

**The overview page asks to build the business even though it should be
loaded** — `AUTO_LOAD_DEMO_DATA` is set to `false`, or the backend is talking
to a `DATABASE_URL` that already has an empty company in it. Press **Build the
business** once; it is open to anyone while the database is empty.

**"The backend did not answer"** — the backend service failed to start. Open
the deployment's logs in Vercel and look at the backend function.

**Changes disappeared** — the server restarted and started again from fresh
demonstration data. Use the PostgreSQL upgrade to keep them.

**`ModuleNotFoundError: psycopg`** — the driver is in
`backend/requirements.txt`, so this means the Root Directory is not
`OpsAgent`.
