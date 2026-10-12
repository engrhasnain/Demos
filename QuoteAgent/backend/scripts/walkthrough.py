"""Run the whole demonstration from the command line.

    python backend/scripts/walkthrough.py            # the full 18,000 part catalogue
    python backend/scripts/walkthrough.py --small    # a smaller catalogue, for a quick check

It loads the demonstration data, then drives all ten steps of the script
through the real HTTP routes, printing what a person would see on screen. If
any step fails, it says which one and why and exits with a non-zero code, so
it works as a smoke test in a pipeline as well as a rehearsal aid.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.db import create_all  # noqa: E402
from app.main import app  # noqa: E402

ADMIN = "admin@hengtai-industrial.example"
PASSWORD = "demo1234"


def heading(text: str) -> None:
    print("\n" + text)
    print("-" * len(text))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the QuoteAgent demonstration.")
    parser.add_argument("--small", action="store_true", help="load a smaller catalogue")
    parser.add_argument("--skip-load", action="store_true", help="use the data already loaded")
    parser.add_argument("--evaluate", action="store_true", help="also run the acceptance criteria")
    parser.add_argument("--json", action="store_true", help="print each step's full payload")
    arguments = parser.parse_args()

    create_all()
    client = TestClient(app)

    if not arguments.skip_load:
        heading("Loading the demonstration data")
        started = time.perf_counter()
        # The loader has to run before anyone can sign in, so it is called directly.
        from app.db import session_scope
        from app.seed import generator
        from app.services import matching

        with session_scope() as session:
            counts = generator.build_demo_data(
                session,
                product_target=2_000 if arguments.small else 18_000,
                customer_target=120 if arguments.small else 1_200,
                progress=lambda stage, done, total: None,
            )
        matching.reset_index()
        print(f"Loaded in {time.perf_counter() - started:.1f} seconds:")
        for key, value in counts.items():
            print(f"  {key.replace('_', ' '):<20} {value:>8,}")

    response = client.post("/api/auth/sign-in", json={"email": ADMIN, "password": PASSWORD})
    if response.status_code != 200:
        print(f"Could not sign in: {response.status_code} {response.text}")
        return 1
    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"

    status = client.get("/api/system/status").json()
    heading("System")
    print(f"  Reasoning engine : {status['reasoning_engine']['active_engine']}")
    print(f"  Database         : {status['database']}")
    print(f"  Parts            : {status['counts']['products']:,}")
    print(f"  Customers        : {status['counts']['customers']:,}")
    print(f"  Cross references : {status['counts']['cross_references']:,}")

    case_id: int | None = None
    failures = 0

    for step in client.get("/api/demo/script").json()["steps"]:
        number = step["number"]
        heading(f"Step {number}: {step['title']}")
        print(f"  What we do   : {step['what_we_do']}")
        started = time.perf_counter()
        response = client.post(
            f"/api/demo/step/{number}", json={"case_id": case_id}
        )
        elapsed = time.perf_counter() - started

        if response.status_code >= 400:
            failures += 1
            print(f"  FAILED ({response.status_code}) after {elapsed:.2f}s")
            print("  " + json.dumps(response.json(), ensure_ascii=False)[:1200])
            continue

        payload = response.json()
        case_id = payload.get("case_id", case_id)
        print(f"  What you see : {payload.get('summary', '')}")
        print(f"  Took         : {elapsed:.2f}s")
        if arguments.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2)[:4000])

    if case_id is not None:
        heading("The case at the end")
        case = client.get(f"/api/cases/{case_id}").json()
        current = case["current_version"]
        print(f"  Reference    : {case['case']['reference']}")
        print(f"  Status       : {case['case']['status_label']}")
        print(f"  Version      : {current['version_number']}")
        print(f"  Terms        : {current['incoterm']} {current['named_place']}")
        print(f"  Total        : {current['totals']['grand_total']} {current['currency']}")
        print(f"  Import duty  : {current['totals']['import_duty']} {current['currency']}")
        print(f"  Margin       : {current['totals']['margin_percent']}%")
        print(f"  Elapsed      : {case['elapsed']}")

        integrity = client.get(f"/api/cases/{case_id}/integrity").json()
        print(f"  Pricing check: {integrity['statement']}")
        if not integrity["ok"]:
            failures += 1
            print("  " + json.dumps(integrity["differences"])[:800])

    if arguments.evaluate:
        heading("Acceptance criteria")
        report = client.post(
            "/api/evaluation/run-now",
            json={"request_count": 20 if arguments.small else 60,
                  "lines_per_request": 25, "revision_pairs": 10},
        ).json()
        for criterion in report["criteria"]:
            mark = {True: "pass", False: "FAIL", None: "not measured"}[criterion["passed"]]
            print(f"  {criterion['name']:<28} {mark:<13} {criterion['measured']}")
        print(f"  {report['statement']}")
        if not report["passed"]:
            failures += 1

    heading("Result")
    if failures:
        print(f"  {failures} step(s) did not pass.")
        return 1
    print("  Every step ran and the pricing check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
