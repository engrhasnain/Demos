# Deploying LedgerFlow to Vercel

One Vercel project, one URL, nothing to set up.

## The zero-setup way

1. On Vercel, **Add New → Project** and import `engrhasnain/Demos`.
2. Set **Root Directory** to `LedgerFlow`.
3. Press **Deploy**. No environment variables.

`LedgerFlow/vercel.json` defines two services in that one project: the Next.js
interface (`frontend/`) and the FastAPI backend (`backend/`, entry
`api/index.py`). Requests to `/api/*` go to the backend and everything else to
the interface, so the interface calls the API on its own address: no CORS and
no backend URL to configure (`frontend/.env.production` leaves
`NEXT_PUBLIC_API_URL` empty on purpose).

Open the URL and sign in as `admin@hengtai-industrial.example` with
`demo1234`, or anybody on the list. The data is already there.

## Where the data comes from

With no `DATABASE_URL` the backend keeps a SQLite file in the function's
scratch space (`/tmp`). When a fresh instance starts it builds the smaller
Hengtai company (40 suppliers, 60 orders and their deliveries, the finance
team) and puts the 19-document batch through the real pipeline, which takes
about 3 seconds. The screens say **"Demonstration data — resets when the
server restarts"**, because it does: each new instance starts again from the
same generated company, and dates are always relative to today.

## Optional settings

None are needed. All are set in the project's **Settings → Environment
Variables**, then redeploy.

| Variable | What it changes |
|---|---|
| `JWT_SECRET` | Signs sign-in tokens. The built-in value is fine for a demonstration; set anything long and random for anything else. |
| `DATABASE_URL` | Keep the data. See below. |
| `AUTO_LOAD_DEMO_DATA` | `false` stops the automatic load on a fresh instance. |
| `MODEL_API_KEY`, `MODEL_BASE_URL` | Read documents with an external model instead of the built-in engine. |

## Optional upgrade: PostgreSQL

To keep data between restarts, create a PostgreSQL database (Neon or Vercel
Postgres both work) and set `DATABASE_URL` to
`postgresql+psycopg://user:password@host/database`. Nothing is loaded
automatically into a real database: build the data once with
`python backend/scripts/walkthrough.py` pointed at it (same `DATABASE_URL`),
then redeploy.

## Two separate projects (still possible)

The backend alone (Root Directory `LedgerFlow/backend`) is detected as a
FastAPI app (`app/main.py`), and the interface alone (Root Directory
`LedgerFlow/frontend`) builds as before. Set `NEXT_PUBLIC_API_URL` on the
interface to the backend's address; optionally narrow `CORS_ORIGINS` on the
backend to the interface's address (it is open by default on Vercel).
