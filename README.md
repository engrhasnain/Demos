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

Each product is **two Vercel projects** from this one repository:

| Vercel project | Root directory | Environment variables |
|---|---|---|
| `<product>-backend` | `<Product>/backend` | `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS` |
| `<product>` (interface) | `<Product>/frontend` | `NEXT_PUBLIC_API_URL` |

- **A hosted PostgreSQL database is required.** Serverless functions have no disk that survives between requests,
  so the local SQLite file cannot be used on Vercel. A free Neon or Vercel Postgres database works; use one
  database per product and write the connection string as `postgresql+psycopg://user:password@host/database`.
- Deploy the backend first, then set `NEXT_PUBLIC_API_URL` on the interface to the backend's address (no trailing
  slash), then set `CORS_ORIGINS` on the backend to the interface's address and redeploy the backend.
- Check the backend at `https://<backend>.vercel.app/api/health` — it should report PostgreSQL.
- Open the interface, press **Load the demonstration data** and choose **A smaller set**, then sign in.

Step-by-step notes are in [`QuoteAgent/docs/deploying-to-vercel.md`](QuoteAgent/docs/deploying-to-vercel.md);
the same steps apply to LedgerFlow and StockSense.
