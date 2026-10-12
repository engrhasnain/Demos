# Deploying QuoteAgent to Vercel

Written for: whoever puts the demonstration on a URL the product owner can
open.

Two Vercel projects out of one repository: the Next.js interface and the
FastAPI backend. They are deployed separately because they have different
build systems, and the interface only needs to know the backend's address.

---

## Before you start

**You need a PostgreSQL database.** This is not optional on Vercel. Serverless
functions have no disk that survives between requests, so the SQLite file the
product uses locally would be gone by the next page load. Any hosted
PostgreSQL works; Vercel Postgres and Neon both take about a minute to create
and both give you a connection string.

The product tells you if you skip this: the status bar across every screen says
the data is in temporary storage and will be lost.

---

## 1. The backend

**Project root:** `MVP/QuoteAgent/backend`

Vercel detects the Python runtime from `requirements.txt`. The entry point is
`api/index.py`, and `vercel.json` rewrites every path to it so FastAPI sees the
original URL and all of its routes work unchanged.

**Environment variables**

| Name | Value | Needed |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://user:password@host/database` | **Yes.** Note the `+psycopg` — a plain `postgres://` string will not work. |
| `JWT_SECRET` | a long random string | **Yes.** The default is a published demonstration value. |
| `CORS_ORIGINS` | your interface URL, e.g. `https://quoteagent.vercel.app` | Recommended. Without it the backend accepts any origin, which is fine for a demonstration and wrong for anything else. |
| `MODEL_API_KEY`, `MODEL_BASE_URL` | a model endpoint | Optional. Without them the built-in engine reads requests and everything still works. |

If your provider gives you a `postgres://…` or `postgresql://…` string, change
the scheme to `postgresql+psycopg://…` and keep the rest.

**Check it**

```
https://your-backend.vercel.app/api/health
https://your-backend.vercel.app/docs
```

`/api/health` should report `"database": "PostgreSQL"`. If it says SQLite, the
`DATABASE_URL` has not reached the function.

## 2. The interface

**Project root:** `MVP/QuoteAgent/frontend`

Vercel detects Next.js and needs no configuration beyond one variable.

| Name | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | `https://your-backend.vercel.app` — no trailing slash |

It is read at build time, so changing it means redeploying the interface.

## 3. Load the data

Open the interface, press **Load the demonstration data**, and choose **A
smaller set**. On serverless hosting the load runs inside the request and the
interface says so instead of showing a progress bar that has nothing behind it.

Then sign in as `admin@hengtai-industrial.example` with `demo1234`. Sending
somebody a link of the form
`https://your-interface.vercel.app/sign-in?as=paul.lee@hengtai-industrial.example`
opens the demonstration directly in that role.

---

## What changes when it runs on Vercel, and why

Serverless is a genuinely different environment, and the product adapts to it
rather than pretending not to notice.

| | A long running server | Vercel |
|---|---|---|
| Database | SQLite file, no setup | PostgreSQL, required |
| Loading the data | A background thread with a progress bar | Inside the request; the bar is not shown |
| Catalogue size | 18,000 parts | 2,000 is the default and the recommendation |
| Documents | Written under `backend/var` | Written to `/tmp`, regenerated on demand |
| Database connections | Pooled and recycled | One per invocation, returned immediately |

**Why the smaller catalogue.** The matcher holds a search index in the
function's memory. A cold start rebuilds it, and over 18,000 parts and 29,000
cross-references from a remote database that takes several seconds on the first
request after an idle period. Two thousand parts rebuilds in a fraction of a
second and every page stays quick. The hard cases in the demonstration all
still fire: the sample request produces exactly the same thirty-three matched
lines, four unclear, one self-contradicting and two not stocked. Run the full
catalogue locally, or on any host that keeps a process alive.

**Why a 60 second function.** `vercel.json` asks for 60 seconds and 1 GB,
because loading the demonstration data and running the acceptance criteria are
both longer than a page request. Everything else answers in well under a
second. On a Hobby plan the ceiling is lower; the smaller catalogue keeps the
load inside it.

**Cold starts.** The first request after an idle period pays for the Python
runtime, the import, and the index rebuild. Expect a second or two. A
demonstration that matters is worth opening once beforehand.

---

## If something is wrong

**"The backend did not answer"** on every screen — `NEXT_PUBLIC_API_URL` is
wrong, or it has a trailing slash, or the interface was built before the
variable was set. Redeploy the interface.

**Sign-in works, every other call fails** — a CORS problem. Set `CORS_ORIGINS`
on the backend to the exact interface origin, with no trailing slash.

**The data disappears** — `DATABASE_URL` is not set, so the product is using a
SQLite file in temporary storage. The warning bar says this on every screen.

**`ModuleNotFoundError: psycopg`** — the driver is in `requirements.txt`, so
this means the backend project root is not `MVP/QuoteAgent/backend`.

**The function times out while loading** — choose the smaller set, or raise
`maxDuration` in `vercel.json` if your plan allows it.
