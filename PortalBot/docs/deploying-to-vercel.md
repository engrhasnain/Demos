# Deploying PortalBot to Vercel

Written for: whoever puts the demonstration on a URL the product owner can
open.

**One Vercel project, one URL, nothing to set up.** No database to create and
no environment variables to fill in. The interface and the API deploy together
from this folder and share one address.

---

## Deploy it (zero setup)

1. In Vercel: **Add New… → Project**, import the repository.
2. **Root Directory:** `PortalBot`. Leave everything else as it is.
3. Press **Deploy**.

When it is live, open the URL and sign in as
`admin@hengtai-industrial.example` with `demo1234`. The data is already
there: the first request after a start fills the database with the
demonstration data, so there is no "load the data" step.

**Check it:** `https://your-project.vercel.app/api/health` should answer
`"database": "ready"`.

---

## How it works

`PortalBot/vercel.json` uses Vercel **services**:

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
  backend address to configure. `npm run dev` still talks to its local
  backend.
- **Data with no database.** On Vercel the backend uses a SQLite file in
  `/tmp`. On the first request after a start it creates the tables and, if the
  database is empty, generates a small demonstration dataset and scripts it
  through a few runs so every screen opens with something to look at: a run
  that was cut off mid-sequence and resumed cleanly with no duplicate
  booking, and a later run that stops, by design, once the carrier's booking
  form changes underneath it. Measured locally this takes well under the
  function time limit.
- **Temporary, and it says so.** Changes last as long as that server does.
  When Vercel starts a new one, it starts again from fresh demonstration data.
  A notice says so: *Demonstration data — resets when the server restarts.*

## Optional settings

None of these are needed for a demonstration.

| Name | What it does |
|---|---|
| `JWT_SECRET` | Signs sign-in tokens. Optional for a demonstration (the published default is used and a warning is logged); set a long random string for anything else. |
| `PORTALBOT_DATA_DIR` | Where the SQLite file lives. Defaults to `/tmp/portalbot` on Vercel. |
| `AUTO_LOAD_DEMO_DATA` | `false` stops the automatic load. `true` turns it on anywhere, including locally (it only ever fills an empty database; it never runs during tests). |
| `AUTO_LOAD_SHIPMENT_TARGET` | Size of the automatic load. Default 60. Larger means a slower first request. |

Environment variables are read when the backend starts, so redeploy after
changing one.

---

## If something is wrong

**The first page sits on loading for a while** — that is the first request
filling the database. It happens once per server.

**"The backend did not answer"** — the backend service failed to start. Open
the deployment's logs in Vercel and look at the backend function.

**Changes disappeared** — the server restarted and started again from fresh
demonstration data. This is a demonstration; there is no "keep it" option.
