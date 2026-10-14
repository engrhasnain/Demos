"""What this thing can be asked, and the exact SQL that answers it.

The decision that makes the rest defensible: **the model does not write
SQL.** Not "the SQL it writes is checked", not "it writes SQL in a
sandbox" — it does not write any. It picks a name from the list below and
fills in parameters, and the parameters are typed and validated before
anything runs.

Why that way round. A technology team killed the last pilot over two
questions: will it show people data they are not allowed to see, and will
it do something nobody approved. Text-to-SQL cannot answer the first one
convincingly, because the answer depends on the model's output every
single time. This can: there are nineteen queries, they were written by a
person, they are in version control, and a reviewer can read all of them
in ten minutes. Anything the model does — including everything it does
wrong, and everything an attacker makes it do — comes out as one of these
nineteen names.

Every query here also carries a ``scope`` column. That is the column the
permission layer attaches its mandatory filter to, and a capability that
reads customer or supplier data without one will not load.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

#: What kind of thing a parameter is, and how it is checked. Nothing
#: reaches SQL as a string the caller chose.
ParameterKind = Literal["customer", "supplier", "part", "days", "date", "number", "text"]


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    kind: ParameterKind
    required: bool = True
    note: str = ""


@dataclass(frozen=True, slots=True)
class Capability:
    """One question this system can answer, and the query that answers it."""

    name: str
    asks: str
    #: Written by a person, reviewed, in version control.
    sql: str
    parameters: tuple[Parameter, ...] = ()
    #: Which column the permission filter attaches to, named as the query
    #: *outputs* it rather than as the query writes it. That distinction
    #: is not pedantry: the filter wraps the query in a select over its
    #: results, so ``c.id`` is not available to bind to — only the alias
    #: ``customer_id`` is. Getting this wrong fails closed, and did: five
    #: capabilities declared ``c.id`` or ``s.id``, which matched nothing,
    #: so every limited account was refused its own accounts. The check
    #: below now allows only the two names that can actually be bound.
    #:
    #: ``None`` means the query reads nothing that belongs to anybody,
    #: which is checked too.
    scope_column: str | None = None
    #: What the rows mean, for the answer.
    columns: tuple[str, ...] = ()
    #: The lowest role that may run it at all.
    needs_role: str = "viewer"
    #: A query that returns counts across the whole company and no rows
    #: belonging to anybody. It cannot be row-scoped, so it is only open
    #: to somebody who is allowed to see the whole company anyway, and
    #: the check below enforces that pairing rather than trusting it.
    whole_company: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "asks": self.asks,
            "sql": self.sql.strip(),
            "parameters": [
                {"name": p.name, "kind": p.kind, "required": p.required, "note": p.note}
                for p in self.parameters
            ],
            "scope_column": self.scope_column,
            "columns": list(self.columns),
            "needs_role": self.needs_role,
            "whole_company": self.whole_company,
        }


#: Only ever read. Checked at load, so a capability that tries to write
#: cannot be added by accident.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|attach|pragma|vacuum)\b",
    re.IGNORECASE,
)

#: An aggregate. These are the dangerous ones, because the permission
#: filter *wraps* a capability's query rather than editing it, so the
#: filter runs after whatever the query computed. A total computed before
#: the filter is a total of other people's money, with a filter applied
#: uselessly to the single row that came out of it. Checked at load.
_AGGREGATE = re.compile(r"\b(count|sum|avg|total|group_concat)\s*\(", re.IGNORECASE)

#: The only two things a grant is expressed in, so the only two columns a
#: capability may be scoped on. Anything else would need a grant nobody
#: issues, and the catalogue refuses to load rather than letting a
#: capability declare a filter that can never attach.
SCOPE_COLUMNS = frozenset({"customer_id", "supplier_id"})


CATALOGUE: list[Capability] = [
    # ---------------------------------------------------------- orders
    Capability(
        name="late_orders_for_customer",
        asks="Which of a customer's orders are late?",
        sql="""
            SELECT o.number        AS order_number,
                   o.placed_on     AS placed_on,
                   o.promised_on   AS promised_on,
                   o.status        AS status,
                   julianday('now') - julianday(o.promised_on) AS days_late,
                   o.customer_id   AS customer_id,
                   c.name          AS customer
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            WHERE o.customer_id = :customer
              AND o.promised_on < date('now')
              AND o.status NOT IN ('delivered', 'cancelled')
            ORDER BY days_late DESC
        """,
        parameters=(Parameter("customer", "customer"),),
        scope_column="customer_id",
        columns=("order_number", "placed_on", "promised_on", "status", "days_late"),
    ),
    Capability(
        name="why_an_order_is_late",
        asks="What is holding one order up?",
        sql="""
            SELECT o.number          AS order_number,
                   o.status          AS status,
                   o.promised_on     AS promised_on,
                   s.state           AS shipment_state,
                   s.exception_kind  AS shipment_exception,
                   s.tracking_number AS tracking_number,
                   o.customer_id     AS customer_id
            FROM orders o
            LEFT JOIN shipments s ON s.order_number = o.number
            WHERE o.number = :order
        """,
        parameters=(Parameter("order", "text"),),
        scope_column="customer_id",
        columns=("order_number", "status", "shipment_state", "shipment_exception"),
    ),
    Capability(
        name="orders_waiting_on_a_part",
        asks="Which orders are waiting on a particular part?",
        sql="""
            SELECT o.number      AS order_number,
                   c.name        AS customer,
                   l.quantity    AS quantity,
                   o.promised_on AS promised_on,
                   o.customer_id AS customer_id
            FROM order_lines l
            JOIN orders o    ON o.id = l.order_id
            JOIN customers c ON c.id = o.customer_id
            WHERE l.part_code = :part
              AND o.status NOT IN ('delivered', 'cancelled')
            ORDER BY o.promised_on
        """,
        parameters=(Parameter("part", "part"),),
        scope_column="customer_id",
        columns=("order_number", "customer", "quantity", "promised_on"),
    ),
    # ------------------------------------------------------- suppliers
    Capability(
        name="supplier_lead_time",
        asks="How long does a supplier actually take, against what they quote?",
        sql="""
            SELECT s.name                  AS supplier,
                   s.quoted_lead_time_days AS quoted_days,
                   AVG(d.actual_days)      AS average_days,
                   MAX(d.actual_days)      AS worst_days,
                   COUNT(d.id)             AS deliveries,
                   s.id                    AS supplier_id
            FROM suppliers s
            LEFT JOIN deliveries d ON d.supplier_id = s.id
            WHERE s.id = :supplier
            GROUP BY supplier_id
        """,
        parameters=(Parameter("supplier", "supplier"),),
        scope_column="supplier_id",
        columns=("supplier", "quoted_days", "average_days", "worst_days", "deliveries"),
    ),
    Capability(
        name="parts_from_supplier",
        asks="Which parts come from a supplier?",
        sql="""
            SELECT p.code        AS part_code,
                   p.description AS description,
                   p.on_hand     AS on_hand,
                   p.supplier_id AS supplier_id
            FROM parts p
            WHERE p.supplier_id = :supplier
            ORDER BY p.code
        """,
        parameters=(Parameter("supplier", "supplier"),),
        scope_column="supplier_id",
        columns=("part_code", "description", "on_hand"),
    ),
    Capability(
        name="customers_exposed_to_supplier",
        asks="If a supplier stops, which customers are hit?",
        sql="""
            SELECT c.name                  AS customer,
                   COUNT(DISTINCT o.id)    AS open_orders,
                   SUM(l.quantity)         AS units_needed,
                   MIN(o.promised_on)      AS soonest_promise,
                   o.customer_id           AS customer_id
            FROM order_lines l
            JOIN parts p     ON p.code = l.part_code
            JOIN orders o    ON o.id = l.order_id
            JOIN customers c ON c.id = o.customer_id
            WHERE p.supplier_id = :supplier
              AND o.status NOT IN ('delivered', 'cancelled')
            GROUP BY customer_id
            ORDER BY soonest_promise
        """,
        parameters=(Parameter("supplier", "supplier"),),
        scope_column="customer_id",
        columns=("customer", "open_orders", "units_needed", "soonest_promise"),
    ),
    Capability(
        name="cover_if_supplier_stops",
        asks="How many weeks of cover is there on a supplier's parts?",
        sql="""
            SELECT p.code                   AS part_code,
                   p.on_hand                AS on_hand,
                   p.weekly_demand          AS weekly_demand,
                   CASE WHEN p.weekly_demand > 0
                        THEN p.on_hand / p.weekly_demand
                        ELSE NULL END       AS weeks_of_cover,
                   p.supplier_id            AS supplier_id
            FROM parts p
            WHERE p.supplier_id = :supplier
              AND p.weekly_demand > 0
            ORDER BY weeks_of_cover
        """,
        parameters=(Parameter("supplier", "supplier"),),
        scope_column="supplier_id",
        columns=("part_code", "on_hand", "weekly_demand", "weeks_of_cover"),
    ),
    # ------------------------------------------------------- customers
    Capability(
        name="customer_overview",
        asks="How is one customer doing overall?",
        sql="""
            SELECT c.name                                       AS customer,
                   COUNT(o.id)                                  AS orders,
                   SUM(CASE WHEN o.status NOT IN ('delivered','cancelled')
                            THEN 1 ELSE 0 END)                  AS open_orders,
                   SUM(o.total)                                 AS total_value,
                   MAX(o.placed_on)                             AS last_order,
                   c.id                                         AS customer_id
            FROM customers c
            LEFT JOIN orders o ON o.customer_id = c.id
            WHERE c.id = :customer
            GROUP BY customer_id
        """,
        parameters=(Parameter("customer", "customer"),),
        scope_column="customer_id",
        columns=("customer", "orders", "open_orders", "total_value", "last_order"),
    ),
    Capability(
        name="customers_with_late_orders",
        asks="Which customers have late orders at the moment?",
        sql="""
            SELECT c.name                 AS customer,
                   COUNT(o.id)            AS late_orders,
                   MAX(julianday('now') - julianday(o.promised_on)) AS worst_days_late,
                   o.customer_id          AS customer_id
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            WHERE o.promised_on < date('now')
              AND o.status NOT IN ('delivered', 'cancelled')
            GROUP BY customer_id
            ORDER BY worst_days_late DESC
        """,
        scope_column="customer_id",
        columns=("customer", "late_orders", "worst_days_late"),
    ),
    # --------------------------------------------------------- invoices
    Capability(
        name="unpaid_invoices_for_customer",
        asks="What does a customer owe?",
        sql="""
            SELECT i.number       AS invoice_number,
                   i.issued_on    AS issued_on,
                   i.due_on       AS due_on,
                   i.total        AS total,
                   julianday('now') - julianday(i.due_on) AS days_overdue,
                   i.customer_id  AS customer_id
            FROM invoices i
            WHERE i.customer_id = :customer
              AND i.paid_on IS NULL
            ORDER BY days_overdue DESC
        """,
        parameters=(Parameter("customer", "customer"),),
        scope_column="customer_id",
        columns=("invoice_number", "issued_on", "due_on", "total", "days_overdue"),
        needs_role="manager",
    ),
    Capability(
        name="money_owed_in_total",
        asks="How much is owed altogether?",
        # Grouped by customer on purpose, and the catalogue check below
        # will not let it be anything else. An ungrouped total would be
        # computed across every invoice in the company and only then
        # handed to the row filter, which would be too late: the figure
        # would already contain money the asker is not allowed to see.
        # Grouped, each row is one account, the filter removes the
        # accounts that are not theirs, and the total is added up from
        # what is left.
        sql="""
            SELECT COUNT(i.id)   AS invoices,
                   SUM(i.total)  AS total_owed,
                   SUM(CASE WHEN i.due_on < date('now') THEN i.total ELSE 0 END)
                                 AS overdue,
                   i.customer_id AS customer_id
            FROM invoices i
            WHERE i.paid_on IS NULL
            GROUP BY customer_id
        """,
        scope_column="customer_id",
        columns=("invoices", "total_owed", "overdue"),
        needs_role="manager",
    ),
    # -------------------------------------------------------- shipments
    Capability(
        name="shipments_held",
        asks="Which shipments are held up, and why?",
        sql="""
            SELECT s.reference      AS shipment,
                   s.order_number   AS order_number,
                   s.state          AS state,
                   s.exception_kind AS reason,
                   c.name           AS customer,
                   o.customer_id    AS customer_id
            FROM shipments s
            JOIN orders o    ON o.number = s.order_number
            JOIN customers c ON c.id = o.customer_id
            WHERE s.exception_kind != ''
            ORDER BY s.id DESC
        """,
        scope_column="customer_id",
        columns=("shipment", "order_number", "state", "reason", "customer"),
    ),
    # ------------------------------------------------------------ stock
    Capability(
        name="stock_for_part",
        asks="How much of a part is there, and what is on order?",
        sql="""
            SELECT p.code          AS part_code,
                   p.description   AS description,
                   p.on_hand       AS on_hand,
                   p.on_order      AS on_order,
                   p.weekly_demand AS weekly_demand,
                   p.supplier_id   AS supplier_id
            FROM parts p
            WHERE p.code = :part
        """,
        parameters=(Parameter("part", "part"),),
        scope_column="supplier_id",
        columns=("part_code", "description", "on_hand", "on_order", "weekly_demand"),
    ),
    Capability(
        name="parts_running_out",
        asks="What is about to run out?",
        sql="""
            SELECT p.code          AS part_code,
                   p.on_hand       AS on_hand,
                   p.weekly_demand AS weekly_demand,
                   p.on_hand / p.weekly_demand AS weeks_of_cover,
                   p.supplier_id   AS supplier_id
            FROM parts p
            WHERE p.weekly_demand > 0
              AND p.on_hand / p.weekly_demand < :weeks
            ORDER BY weeks_of_cover
        """,
        parameters=(Parameter("weeks", "number", note="weeks of cover"),),
        scope_column="supplier_id",
        columns=("part_code", "on_hand", "weekly_demand", "weeks_of_cover"),
    ),
    # ------------------------------------------------------- the desk
    Capability(
        name="open_tickets",
        asks="What is the service desk holding?",
        sql="""
            SELECT t.reference    AS ticket,
                   t.reason       AS reason,
                   c.name         AS customer,
                   t.raised_on    AS raised_on,
                   t.customer_id  AS customer_id
            FROM tickets t
            LEFT JOIN customers c ON c.id = t.customer_id
            WHERE t.status = 'open'
            ORDER BY t.raised_on
        """,
        scope_column="customer_id",
        columns=("ticket", "reason", "customer", "raised_on"),
    ),
    # ------------------------------------------------------- reference
    Capability(
        name="find_customer",
        asks="Which customer is this?",
        sql="""
            SELECT c.id   AS customer_id,
                   c.code AS code,
                   c.name AS customer,
                   c.country AS country
            FROM customers c
            WHERE c.name LIKE :text OR c.code LIKE :text
            ORDER BY c.name
            LIMIT 10
        """,
        parameters=(Parameter("text", "text"),),
        scope_column="customer_id",
        columns=("code", "customer", "country"),
    ),
    Capability(
        name="find_supplier",
        asks="Which supplier is this?",
        sql="""
            SELECT s.id   AS supplier_id,
                   s.code AS code,
                   s.name AS supplier,
                   s.country AS country
            FROM suppliers s
            WHERE s.name LIKE :text OR s.code LIKE :text
            ORDER BY s.name
            LIMIT 10
        """,
        parameters=(Parameter("text", "text"),),
        scope_column="supplier_id",
        columns=("code", "supplier", "country"),
    ),
    Capability(
        name="supplier_shutdowns",
        asks="When do suppliers shut, and for how long?",
        sql="""
            SELECT s.name            AS supplier,
                   s.country         AS country,
                   s.shutdown_from   AS shuts_on,
                   s.shutdown_to     AS reopens_on,
                   julianday(s.shutdown_to) - julianday(s.shutdown_from) AS days_shut,
                   s.id              AS supplier_id
            FROM suppliers s
            WHERE s.shutdown_from IS NOT NULL
            ORDER BY s.shutdown_from
        """,
        scope_column="supplier_id",
        columns=("supplier", "country", "shuts_on", "reopens_on", "days_shut"),
    ),
    Capability(
        name="headline_numbers",
        asks="How is the business doing this week?",
        sql="""
            SELECT (SELECT COUNT(*) FROM orders
                      WHERE status NOT IN ('delivered','cancelled'))  AS open_orders,
                   (SELECT COUNT(*) FROM orders
                      WHERE promised_on < date('now')
                        AND status NOT IN ('delivered','cancelled'))  AS late_orders,
                   (SELECT COUNT(*) FROM shipments
                      WHERE exception_kind != '')                     AS held_shipments,
                   (SELECT COUNT(*) FROM tickets WHERE status='open') AS open_tickets
        """,
        scope_column=None,
        columns=("open_orders", "late_orders", "held_shipments", "open_tickets"),
        needs_role="manager",
        whole_company=True,
    ),
]


BY_NAME: dict[str, Capability] = {c.name: c for c in CATALOGUE}


def _check_the_catalogue() -> None:
    """Refuse to start on a capability that breaks the rules.

    Three rules, all of them things a reviewer would otherwise have to
    remember every time somebody adds a query:

    * read only;
    * anything touching customer, supplier or ticket data declares the
      column its permission filter attaches to;
    * that column is actually selected, so the filter has something to
      bind to and the answer can show whose data it is.
    """
    for capability in CATALOGUE:
        if _FORBIDDEN.search(capability.sql):
            raise RuntimeError(
                f"{capability.name} is not read only. Capabilities never write."
            )
        if ";" in capability.sql.strip().rstrip(";"):
            raise RuntimeError(
                f"{capability.name} has more than one statement in it."
            )
        touches = any(
            table in capability.sql.lower()
            for table in ("customers", "suppliers", "tickets", "invoices", "parts")
        )
        if touches and capability.scope_column is None and not capability.whole_company:
            raise RuntimeError(
                f"{capability.name} reads data that belongs to somebody and "
                "declares no scope column."
            )
        if capability.whole_company:
            if capability.scope_column is not None:
                raise RuntimeError(
                    f"{capability.name} cannot be both whole-company and scoped."
                )
            if capability.needs_role not in {"manager", "director", "administrator"}:
                raise RuntimeError(
                    f"{capability.name} returns whole-company figures, so it has "
                    "to require a role that is allowed to see the whole company."
                )
        if capability.scope_column:
            column = capability.scope_column
            if column not in SCOPE_COLUMNS:
                raise RuntimeError(
                    f"{capability.name} is scoped on {column!r}, and the only "
                    f"columns a grant can be bound to are "
                    f"{', '.join(sorted(SCOPE_COLUMNS))}."
                )
            # It has to be the name the query *outputs*, because the
            # filter wraps the query rather than editing it. An alias in
            # the select list is the only thing that proves that.
            if f"AS {column}" not in capability.sql:
                raise RuntimeError(
                    f"{capability.name} declares {column} but does not select "
                    f"it under that name. Add 'AS {column}' to the query, or "
                    "the permission filter has nothing to bind to and the "
                    "capability is refused to everybody."
                )
            # The rule that matters most and is easiest to get wrong,
            # because the query looks right and the answer looks right
            # until somebody with partial grants asks it.
            if _AGGREGATE.search(capability.sql):
                after = capability.sql.lower().split("group by")
                if len(after) < 2 or column not in after[1]:
                    raise RuntimeError(
                        f"{capability.name} adds figures up and is row-scoped "
                        f"on {column}, so it has to GROUP BY {column}. "
                        "Otherwise the sum is taken across everybody and the "
                        "permission filter arrives after the money has already "
                        "been counted."
                    )


_check_the_catalogue()


def is_known(name: str) -> bool:
    return name in BY_NAME
