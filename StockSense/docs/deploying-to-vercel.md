# Deploying StockSense to Vercel

One Vercel project, one address, nothing to set up first: no database, no
environment variables.

## Deploy

1. On Vercel: **Add New → Project** and import `engrhasnain/Demos`.
2. Set **Root Directory** to `StockSense`.
3. Press **Deploy**.

Open the address Vercel gives you and sign in as
`admin@hengtai-industrial.example` with `demo1234` (everybody on the list uses
`demo1234`).

## How it fits together

`StockSense/vercel.json` declares two **services** in the one project:

| Service | Folder | Serves |
|---|---|---|
| `frontend` | `frontend/` | the Next.js interface, at every path except `/api/*` |
| `backend` | `backend/` | the FastAPI app (`api/index.py`), at `/api/*` |

The interface and the API share one origin, so the interface calls `/api/...`
relatively (`frontend/.env.production` leaves `NEXT_PUBLIC_API_URL` empty):
no backend address to configure and no CORS.

## The data

With no `DATABASE_URL`, the backend keeps its data in a SQLite file in the
function's `/tmp`. On the first request after a cold start it builds a compact
demonstration company — 600 parts, 25 suppliers, two years of weekly history —
then works out this week's orders and replays a slice of the year, so every
screen has real numbers at once. That takes about 4–6 seconds, once per
instance.

**Demonstration data — resets when the server restarts.** Anything changed is
gone when Vercel recycles the instance, and separate instances each build
their own (identical) copy. The interface says so in a bar under the header.

## Optional settings

| Variable | Default | What it does |
|---|---|---|
| `JWT_SECRET` | a published demo value | Signs sign-in tokens. Fine for a demonstration; set anything long and random otherwise (required when `ENVIRONMENT` is not `demo`). |
| `AUTO_LOAD_DEMO_DATA` | `true` | `false` starts empty; the sign-in page then offers **Build the company** (open only while the database is empty). |
| `DATABASE_URL` | SQLite in `/tmp` | See below. |

## Upgrade: keep the data (PostgreSQL)

To make the data survive restarts, create a PostgreSQL database (Neon or
Vercel Postgres both work) and set on the project:

```
DATABASE_URL=postgresql+psycopg://user:password@host/database
JWT_SECRET=<anything long and random>
```

Redeploy. Nothing is loaded automatically on PostgreSQL: open the site, press
**Build the company** on the sign-in page, then sign in as the administrator
and work out the week. On serverless hosting a catalogue rebuild is capped at
6,000 parts to stay inside the function time limit.

## Local development is unchanged

`npm run dev` (port 3002) talks to the backend at `http://127.0.0.1:8002`.
The auto-load never runs locally or in tests — only when serverless and on
SQLite.
