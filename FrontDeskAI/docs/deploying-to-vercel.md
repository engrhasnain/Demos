# Deploying FrontDesk to Vercel

Written for: whoever puts the demonstration on a URL the product owner can
open.

**One Vercel project, one URL, nothing to set up.** No database to create and
no environment variables to fill in. The interface and the API deploy
together from this folder and share one address.

---

## Deploy it (zero setup)

1. In Vercel: **Add New… → Project**, import the repository.
2. **Root Directory:** `FrontDeskAI`. Leave everything else as it is.
3. Press **Deploy**.

When it is live, open the URL. A small company is already there: the first
request after a start fills the database with a handful of customers,
orders, a couple of conversations and a booked technician visit, so there is
no "load the data" step. Sign in at `/sign-in` as
`admin@hengtai-industrial.example` with `demo1234`, or open `/chat` directly
— the customer chat needs no sign-in at all, on this deployment or any
other.

**Check it:** `https://your-project.vercel.app/api/health` should answer
`"status": "ready"` (the route lives at `/api/health` under the hood).

---

## How it works

`FrontDeskAI/vercel.json` uses Vercel **services**:

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
  so the production interface calls `/api/...` on its own address: no CORS,
  no backend address to configure. `npm run dev` still talks to
  `http://127.0.0.1:8003`.
- **Data with no database.** On Vercel the backend uses a SQLite file in
  `/tmp`. On the first request after a start it creates the tables and, if
  the database is empty, generates a small demonstration company: 20
  customers, about 60 orders, six technicians, and four live conversations —
  one never verified, one verified and answered from its own records, one
  return waiting for a person to approve (the one handover example), and one
  technician visit actually booked. It is generated rather than copied, so
  every date is relative to today. It takes well under the platform's
  function limit, once per server; requests that arrive meanwhile wait for
  it.
- **The guided first run still works if the load is ever skipped.** Visit
  "/" before anything has loaded (for example after switching
  `AUTO_LOAD_DEMO_DATA` off) and the same "Build the company" screen a
  long-running server uses appears, open without signing in — because on a
  brand new database nobody could sign in to press it. As soon as any
  account or any customer exists, loading again needs an administrator.
- **Temporary, and it says so.** Changes last as long as that server does.
  When Vercel starts a new one, it starts again from fresh demonstration
  data. A thin bar across the top says *Demonstration data — resets when the
  server restarts.*
- **LINE stays off.** Nothing is sent anywhere unless
  `LINE_CHANNEL_ACCESS_TOKEN` is set; the `/line` page in this interface
  shows what the same engine would have said, recorded rather than pushed to
  a phone.

## Optional settings

None of these are needed for a demonstration.

| Name | What it does |
|---|---|
| `JWT_SECRET` | Signs sign-in tokens. Optional for a demonstration (the published default is used and a warning is logged); set a long random string for anything else. |
| `DATABASE_URL` | Keeps the data. See the upgrade below. |
| `AUTO_LOAD_DEMO_DATA` | `false` stops the automatic load. `true` turns it on anywhere, including locally or on PostgreSQL (it only ever fills an empty database). |
| `AUTO_LOAD_CUSTOMER_TARGET`, `AUTO_LOAD_ORDER_TARGET` | Size of the automatic load. Defaults 20 and 60. Larger means a slower first request. |
| `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN` | Puts the LINE webhook live. Without them it is implemented and tested but not operated. |
| `MODEL_API_KEY`, `MODEL_BASE_URL` | A hosted model to pick the intent and phrase a reply. Without it the built-in engine does both and everything still works. |

Environment variables are read when the backend starts, so redeploy after
changing one.

## Optional upgrade: PostgreSQL, so the data persists

1. Create a PostgreSQL database (Neon or Vercel Postgres take about a
   minute).
2. In the project's **Settings → Environment Variables**, add
   `DATABASE_URL`. Write the scheme as
   `postgresql+psycopg://user:password@host/database`; a plain
   `postgres://` string will not work, so change the scheme and keep the
   rest.
3. Add `JWT_SECRET` as well, then redeploy.
4. Open the site and press **Build the company** on the first run, or set
   `AUTO_LOAD_DEMO_DATA=true` to have the first request do it.

`/api/health` then reports `"database": "ready"` against a database that
keeps its rows, and the bar at the top disappears.
