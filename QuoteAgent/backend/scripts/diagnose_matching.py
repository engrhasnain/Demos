"""Show, line by line, what the matcher did with the sample bill of materials.

    python backend/scripts/diagnose_matching.py

Useful while tuning: it prints each line, what was read out of it, what it
matched to and why, so a wrong answer can be traced to the step that produced
it rather than guessed at.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import create_all, session_scope  # noqa: E402
from app.domain.partnumbers import parse_specification  # noqa: E402
from app.seed.samples import build_bill_of_materials  # noqa: E402
from app.services import matching  # noqa: E402


def main() -> int:
    create_all()
    with session_scope() as session:
        rows = build_bill_of_materials(session)
        index = matching.get_index(session, rebuild=True)

        correct = flagged = wrong = 0
        print(f"{'#':>3}  {'tag':<26} {'result':<22} line")
        print("-" * 118)
        for row in rows:
            specification = parse_specification(row["description"])
            result = matching.match_line(
                session, row["description"], specification=specification, index=index
            )
            expected = row["expect"]
            got = result.product.sku if result.product else ""

            if expected.startswith("question:") or row["tag"] in {
                "missing_attribute", "conflicting_specification"
            }:
                outcome = "flagged (wanted)" if result.status != "matched" else "NOT FLAGGED"
                flagged += 1 if result.status != "matched" else 0
            elif row["tag"] == "non_catalogue":
                outcome = "no catalogue match" if result.status == "non_catalogue" else f"matched {got}"
            elif expected and expected not in {"attribute", "supplier"}:
                if got == expected:
                    outcome = "correct"
                    correct += 1
                else:
                    outcome = f"WRONG -> {got or result.status}"
                    wrong += 1
            else:
                outcome = result.status

            print(f"{row['item']:>3}  {row['tag']:<26} {outcome:<22} {row['description'][:60]}")
            if outcome.startswith("WRONG") or outcome == "NOT FLAGGED":
                print(f"     read as: {specification.family} {specification.attributes}")
                print(f"     missing: {specification.missing} conflicts: {len(specification.conflicts)}")
                for reason in result.reasons[:2]:
                    print(f"     reason : {reason}")
                for alternative in result.alternatives[:2]:
                    print(f"     also   : {alternative['sku']} score {alternative['score']}")

        print("-" * 118)
        print(f"correct {correct}, wrong {wrong}, flagged as intended {flagged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
