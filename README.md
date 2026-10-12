# Demos

Three working products for **Hengtai Industrial Supply**, a fictional Taiwan–US distributor of industrial
fasteners, bearings and pneumatic components. Each folder is a complete product: a **FastAPI** backend and a
**Next.js** interface.

| Product | Folder | What it does |
|---|---|---|
| **QuoteAgent** | [`QuoteAgent/`](QuoteAgent/) | Turns a messy, multi-line request for quotation into a priced, approved quote the same day. It asks instead of guessing and never invents a price. |
| **LedgerFlow** | [`LedgerFlow/`](LedgerFlow/) | Reads supplier invoices, checks them against the purchase order and the delivery, routes approvals and posts to the ledger — without ever paying the same invoice twice. |
| **StockSense** | [`StockSense/`](StockSense/) | Forecasts demand and recommends what to reorder under a weekly cash cap, for thousands of parts that mostly sell nothing, around supplier shutdowns. |

Every product runs with no key and no account: a deterministic built-in engine does the work, every number on
screen can be clicked to show how it was worked out, and each product ships its acceptance checks as tests.

## Run one locally

```bash
cd QuoteAgent            # or LedgerFlow, StockSense

# terminal one: the backend
python -m venv .venv
.venv\Scripts\activate   # macOS and Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn app.main:app --reload --app-dir backend

# terminal two: the interface
cd frontend && npm install && npm run dev
```

Open the interface, press **Load the demonstration data**, then sign in as
`admin@hengtai-industrial.example` with `demo1234`.

| Product | Interface | Backend |
|---|---|---|
| QuoteAgent | http://localhost:3000 | http://localhost:8000 |
| LedgerFlow | http://localhost:3001 | http://localhost:8001 |
| StockSense | http://localhost:3002 | http://localhost:8002 |

## Deploy on Vercel

Each product is **one Vercel project with zero setup**: no database to create, no environment variables.

1. **Add New… → Project**, import `engrhasnain/Demos`.
2. **Root Directory:** the product folder, e.g. `QuoteAgent`. Leave everything else as it is.
3. **Deploy**, open the URL and sign in as `admin@hengtai-industrial.example` with `demo1234`.

The product's `vercel.json` runs the interface and the API as two Vercel services behind one URL: `/api/*` goes to
the FastAPI backend, everything else to the Next.js interface, so there is no CORS and no backend address to set.
The backend keeps a SQLite file in temporary storage and fills it with the demonstration data on the first request
after a start, so it opens with data. The data is temporary and resets when the server restarts — fine for a
demonstration.

**Optional upgrade:** to keep the data, set `DATABASE_URL` to a PostgreSQL database
(`postgresql+psycopg://user:password@host/database`) and `JWT_SECRET` to a long random string, then redeploy.

Details: [`QuoteAgent/docs/deploying-to-vercel.md`](QuoteAgent/docs/deploying-to-vercel.md).
