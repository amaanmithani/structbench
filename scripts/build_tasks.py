"""Generate data/tasks.jsonl.

The task texts and ground truth are hand-written below; this script only
assembles them with their schemas so the JSONL stays consistent. Run:

    uv run python scripts/build_tasks.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

S = dict[str, Any]


def obj(props: S, optional: tuple[str, ...] = ()) -> S:
    return {
        "type": "object",
        "properties": props,
        "required": [k for k in props if k not in optional],
        "additionalProperties": False,
    }


def arr(items: S, **kw: Any) -> S:
    return {"type": "array", "items": items, **kw}


STR: S = {"type": "string"}
INT: S = {"type": "integer"}
NUM: S = {"type": "number"}
BOOL: S = {"type": "boolean"}
DATE: S = {"type": "string", "description": "ISO date, YYYY-MM-DD"}
TIME: S = {"type": "string", "description": "24-hour time, HH:MM"}


def enum(*vals: str) -> S:
    return {"type": "string", "enum": list(vals)}


def rng(t: str, lo: float | None = None, hi: float | None = None) -> S:
    s: S = {"type": t}
    if lo is not None:
        s["minimum"] = lo
    if hi is not None:
        s["maximum"] = hi
    return s


def nullable(s: S) -> S:
    return {"anyOf": [s, {"type": "null"}]}


# ------------------------------------------------------------------ Level 1: flat

CONTACT = obj({"name": STR, "company": STR, "email": STR, "phone": STR, "city": STR})
INVOICE_SUMMARY = obj(
    {
        "invoice_number": STR,
        "vendor": STR,
        "issue_date": DATE,
        "total_amount": NUM,
        "currency": {"type": "string", "description": "ISO 4217 code, e.g. USD"},
        "paid": BOOL,
    }
)
EVENT = obj(
    {
        "title": STR,
        "date": DATE,
        "start_time": TIME,
        "venue": STR,
        "capacity": INT,
        "is_free": BOOL,
    }
)
BOOK = obj({"title": STR, "author": STR, "year": INT, "pages": INT, "publisher": STR})

# --------------------------------------------------------- Level 2: nested + arrays

RECIPE = obj(
    {
        "name": STR,
        "servings": INT,
        "prep_time_minutes": INT,
        "ingredients": arr(
            obj(
                {
                    "item": STR,
                    "quantity": NUM,
                    "unit": {
                        "type": "string",
                        "description": 'unit of measure as written; use "whole" for counted items',
                    },
                }
            )
        ),
        "tools": arr(STR),
    }
)
JOB_POST = obj(
    {
        "title": STR,
        "company": obj({"name": STR, "location": obj({"city": STR, "country": STR})}),
        "salary": obj({"min": NUM, "max": NUM, "currency": STR}),
        "skills": arr(STR),
    }
)
ORDER = obj(
    {
        "order_id": STR,
        "customer": obj({"name": STR, "email": STR}),
        "items": arr(obj({"sku": STR, "qty": INT, "unit_price": NUM})),
        "shipping_address": obj({"street": STR, "city": STR, "postal_code": STR}),
    }
)

# ------------------------------------------- Level 3: enums + required + numeric ranges

BUG_REPORT = obj(
    {
        "title": STR,
        "severity": enum("critical", "high", "medium", "low"),
        "component": enum("auth", "billing", "search", "ui", "api", "storage"),
        "status": enum("new", "confirmed", "in_progress", "wont_fix"),
        "priority": rng("integer", 1, 5),
        "reproducible": BOOL,
        "affected_version": STR,
        "estimated_hours": rng("number", 0, 200),
    }
)
REVIEW = obj(
    {
        "product": STR,
        "rating": rng("integer", 1, 5),
        "sentiment": enum("positive", "negative", "mixed"),
        "would_recommend": BOOL,
        "price_paid": rng("number", 0),
        "aspects": arr(
            obj(
                {
                    "aspect": enum("battery", "screen", "camera", "price", "build", "support"),
                    "sentiment": enum("positive", "negative", "neutral"),
                }
            )
        ),
    }
)
FLIGHT = obj(
    {
        "passenger_name": STR,
        "trip_type": enum("one_way", "round_trip"),
        "cabin": enum("economy", "premium_economy", "business", "first"),
        "passengers": rng("integer", 1, 9),
        "checked_bags": rng("integer", 0, 4),
        "total_fare": rng("number", 0),
        "segments": arr(
            obj(
                {
                    "from": {"type": "string", "pattern": "^[A-Z]{3}$"},
                    "to": {"type": "string", "pattern": "^[A-Z]{3}$"},
                    "date": DATE,
                }
            ),
            minItems=1,
        ),
    }
)

# ------------------------------ Level 4: deeply nested, optional fields, unions

CONTACT_UNION: S = {
    "anyOf": [
        obj({"kind": {"const": "email"}, "address": STR}),
        obj({"kind": {"const": "phone"}, "number": STR}),
    ]
}
INCIDENT = obj(
    {
        "incident": obj(
            {
                "id": STR,
                "reported_at": DATE,
                "reporter": obj({"name": STR, "contact": CONTACT_UNION}),
            }
        ),
        "systems": arr(
            obj(
                {
                    "name": STR,
                    "impact": obj(
                        {"level": enum("outage", "degraded", "none"), "details": STR},
                        optional=("details",),
                    ),
                }
            )
        ),
        "resolution": {
            "anyOf": [
                obj(
                    {"status": {"const": "resolved"}, "root_cause": STR, "fixed_by": STR},
                    optional=("fixed_by",),
                ),
                obj({"status": {"const": "open"}, "eta_hours": NUM}, optional=("eta_hours",)),
            ]
        },
        "notes": STR,
    },
    optional=("notes",),
)
PAYMENT_METHOD: S = {
    "anyOf": [
        obj({"kind": {"const": "card"}, "brand": STR, "last4": STR}),
        obj({"kind": {"const": "bank_transfer"}, "bank": STR, "reference": STR}),
        obj({"kind": {"const": "cash"}}),
    ]
}
TRANSACTION = obj(
    {
        "payer": obj({"name": STR, "method": PAYMENT_METHOD}),
        "line_items": arr(
            obj(
                {"description": STR, "amount": NUM, "discount": nullable(NUM)},
                optional=("discount",),
            )
        ),
        "shipping": obj(
            {
                "carrier": STR,
                "address": obj({"street": STR, "city": STR, "country": STR}),
            }
        ),
    },
    optional=("shipping",),
)
SCHEDULE = obj(
    {
        "event": STR,
        "sessions": arr(
            obj(
                {
                    "title": STR,
                    "speaker": nullable(
                        obj({"name": STR, "affiliation": STR}, optional=("affiliation",))
                    ),
                    "slot": obj({"day": rng("integer", 1, 3), "start": TIME}),
                    "room": STR,
                },
                optional=("room",),
            )
        ),
    }
)

# ------------------------------------------------------------------------ tasks

TASKS: list[S] = []


def add(
    tid: str, level: int, domain: str, schema: S, instruction: str, text: str, expected: S
) -> None:
    TASKS.append(
        {
            "id": tid,
            "difficulty": level,
            "domain": domain,
            "instruction": instruction,
            "text": text.strip(),
            "schema": schema,
            "expected": expected,
        }
    )


C_INS = "Extract the sender's contact details from this email signature."
add(
    "l1-contact-01",
    1,
    "contact",
    CONTACT,
    C_INS,
    """
Thanks again for the quick turnaround on the proposal.

Best,
Priya Raman
Senior Account Manager | Northwind Logistics
priya.raman@northwind-logistics.com | +1 (415) 555-0142
Based in San Francisco
""",
    {
        "name": "Priya Raman",
        "company": "Northwind Logistics",
        "email": "priya.raman@northwind-logistics.com",
        "phone": "+1 (415) 555-0142",
        "city": "San Francisco",
    },
)
add(
    "l1-contact-02",
    1,
    "contact",
    CONTACT,
    C_INS,
    """
Cheers -- and let me know if Thursday works for the site visit.
--
Tomás Herrera
Field Engineer, Brightline Solar
Office: Austin
M: 512-555-0199
tomas@brightlinesolar.io
""",
    {
        "name": "Tomás Herrera",
        "company": "Brightline Solar",
        "email": "tomas@brightlinesolar.io",
        "phone": "512-555-0199",
        "city": "Austin",
    },
)
add(
    "l1-contact-03",
    1,
    "contact",
    CONTACT,
    C_INS,
    """
Regards,
Hannah Okafor (she/her)
Clinical Research Lead
Meridian Health Partners, 44 King Street, Manchester
t: +44 161 555 0107
e: h.okafor@meridianhp.co.uk
""",
    {
        "name": "Hannah Okafor",
        "company": "Meridian Health Partners",
        "email": "h.okafor@meridianhp.co.uk",
        "phone": "+44 161 555 0107",
        "city": "Manchester",
    },
)

I_INS = "Summarise this invoice."
add(
    "l1-invoice-01",
    1,
    "invoice",
    INVOICE_SUMMARY,
    I_INS,
    """
INVOICE #INV-20931
From: Acme Office Supply Co.
Date issued: March 4, 2025
Bill to: Harbor Dental Group
Printer paper (10 reams) ........ $54.90
Toner cartridge x2 .............. $189.00
Subtotal: $243.90   Tax: $19.51
TOTAL DUE: $263.41 (USD)
Payment status: UNPAID - due within 30 days
""",
    {
        "invoice_number": "INV-20931",
        "vendor": "Acme Office Supply Co.",
        "issue_date": "2025-03-04",
        "total_amount": 263.41,
        "currency": "USD",
        "paid": False,
    },
)
add(
    "l1-invoice-02",
    1,
    "invoice",
    INVOICE_SUMMARY,
    I_INS,
    """
Rechnung / Invoice No. 2025-0457
Kraus Webdesign GmbH, Berlin
Issued 17.06.2025
Website maintenance, May 2025: EUR 1,200.00
VAT 19%: EUR 228.00
Total: EUR 1,428.00
Paid in full on 20.06.2025 - thank you!
""",
    {
        "invoice_number": "2025-0457",
        "vendor": "Kraus Webdesign GmbH",
        "issue_date": "2025-06-17",
        "total_amount": 1428.00,
        "currency": "EUR",
        "paid": True,
    },
)
add(
    "l1-invoice-03",
    1,
    "invoice",
    INVOICE_SUMMARY,
    I_INS,
    """
Maple Leaf Catering
Invoice: MLC-118
Invoice date: 2024-11-29
Event: Year-end staff lunch (45 guests)
Amount: CAD 2,317.50
Status: Payment received by e-transfer.
""",
    {
        "invoice_number": "MLC-118",
        "vendor": "Maple Leaf Catering",
        "issue_date": "2024-11-29",
        "total_amount": 2317.50,
        "currency": "CAD",
        "paid": True,
    },
)

E_INS = "Extract the event details from this announcement."
add(
    "l1-event-01",
    1,
    "event",
    EVENT,
    E_INS,
    """
Join us for "Intro to Home Composting", a hands-on workshop at the Riverside Community
Garden on Saturday, April 12, 2025. Doors open at 10:30 AM. Space is limited to 25
participants. Free entry - just bring gloves!
""",
    {
        "title": "Intro to Home Composting",
        "date": "2025-04-12",
        "start_time": "10:30",
        "venue": "Riverside Community Garden",
        "capacity": 25,
        "is_free": True,
    },
)
add(
    "l1-event-02",
    1,
    "event",
    EVENT,
    E_INS,
    """
Title: "Scaling pandas with DuckDB" (PyData Lisbon Meetup #14)
When: 2025-09-18, 18:45
Where: LX Factory, Building G
Tickets: EUR 5 (covers snacks), max 120 attendees.
""",
    {
        "title": "Scaling pandas with DuckDB",
        "date": "2025-09-18",
        "start_time": "18:45",
        "venue": "LX Factory, Building G",
        "capacity": 120,
        "is_free": False,
    },
)

B_INS = "Extract the bibliographic details of the book described."
add(
    "l1-book-01",
    1,
    "book",
    BOOK,
    B_INS,
    """
Just finished "The Quiet Engine" by Marguerite Doyle - published by Harrow & Finch in 2019,
a hefty 412 pages but it flew by.
""",
    {
        "title": "The Quiet Engine",
        "author": "Marguerite Doyle",
        "year": 2019,
        "pages": 412,
        "publisher": "Harrow & Finch",
    },
)
add(
    "l1-book-02",
    1,
    "book",
    BOOK,
    B_INS,
    """
Catalogue entry: Kenji Watanabe. Rivers of Salt: A History of the Inland Sea.
Osaka University Press, 2008. xii + 286 pp. (286 numbered pages)
""",
    {
        "title": "Rivers of Salt: A History of the Inland Sea",
        "author": "Kenji Watanabe",
        "year": 2008,
        "pages": 286,
        "publisher": "Osaka University Press",
    },
)

# ---- Level 2
R_INS = "Extract the recipe as structured data."
add(
    "l2-recipe-01",
    2,
    "recipe",
    RECIPE,
    R_INS,
    """
Weeknight Lemon Garlic Pasta (serves 4, 20 minutes prep)
You'll need: 400 g spaghetti, 3 cloves garlic, 2 tbsp olive oil, 1 lemon, 50 g parmesan.
Equipment: large pot, skillet, microplane.
""",
    {
        "name": "Weeknight Lemon Garlic Pasta",
        "servings": 4,
        "prep_time_minutes": 20,
        "ingredients": [
            {"item": "spaghetti", "quantity": 400, "unit": "g"},
            {"item": "garlic", "quantity": 3, "unit": "cloves"},
            {"item": "olive oil", "quantity": 2, "unit": "tbsp"},
            {"item": "lemon", "quantity": 1, "unit": "whole"},
            {"item": "parmesan", "quantity": 50, "unit": "g"},
        ],
        "tools": ["large pot", "skillet", "microplane"],
    },
)
add(
    "l2-recipe-02",
    2,
    "recipe",
    RECIPE,
    R_INS,
    """
Banana Oat Muffins - makes 12 muffins. Prep time: 15 min.
Ingredients
- 3 bananas
- 200 g rolled oats
- 2 eggs
- 120 ml milk
- 1 tsp baking powder
Tools: muffin tin, mixing bowl
""",
    {
        "name": "Banana Oat Muffins",
        "servings": 12,
        "prep_time_minutes": 15,
        "ingredients": [
            {"item": "bananas", "quantity": 3, "unit": "whole"},
            {"item": "rolled oats", "quantity": 200, "unit": "g"},
            {"item": "eggs", "quantity": 2, "unit": "whole"},
            {"item": "milk", "quantity": 120, "unit": "ml"},
            {"item": "baking powder", "quantity": 1, "unit": "tsp"},
        ],
        "tools": ["muffin tin", "mixing bowl"],
    },
)
add(
    "l2-recipe-03",
    2,
    "recipe",
    RECIPE,
    R_INS,
    """
Chana Masala. Feeds 6. Takes about 25 minutes to prep.
Grab 2 cans chickpeas, 1 onion, 400 g crushed tomatoes, 2 tsp garam masala and 1 tbsp ginger paste.
You'll use a heavy-bottomed pan and a wooden spoon.
""",
    {
        "name": "Chana Masala",
        "servings": 6,
        "prep_time_minutes": 25,
        "ingredients": [
            {"item": "chickpeas", "quantity": 2, "unit": "cans"},
            {"item": "onion", "quantity": 1, "unit": "whole"},
            {"item": "crushed tomatoes", "quantity": 400, "unit": "g"},
            {"item": "garam masala", "quantity": 2, "unit": "tsp"},
            {"item": "ginger paste", "quantity": 1, "unit": "tbsp"},
        ],
        "tools": ["heavy-bottomed pan", "wooden spoon"],
    },
)

J_INS = "Extract the job posting details. Salary figures are annual amounts."
add(
    "l2-job-01",
    2,
    "job_post",
    JOB_POST,
    J_INS,
    """
Backend Engineer (Go) - Tidewater Analytics
Location: Toronto, Canada (hybrid)
Compensation: CAD 110,000 - 135,000 per year
We're looking for someone comfortable with Go, PostgreSQL, Kafka and Kubernetes.
""",
    {
        "title": "Backend Engineer (Go)",
        "company": {
            "name": "Tidewater Analytics",
            "location": {"city": "Toronto", "country": "Canada"},
        },
        "salary": {"min": 110000, "max": 135000, "currency": "CAD"},
        "skills": ["Go", "PostgreSQL", "Kafka", "Kubernetes"],
    },
)
add(
    "l2-job-02",
    2,
    "job_post",
    JOB_POST,
    J_INS,
    """
Hiring: Data Analyst at Greenleaf Grocers, based in Leeds, United Kingdom.
Pay band GBP 32k-38k. Must know SQL and Tableau; Python is a plus.
""",
    {
        "title": "Data Analyst",
        "company": {
            "name": "Greenleaf Grocers",
            "location": {"city": "Leeds", "country": "United Kingdom"},
        },
        "salary": {"min": 32000, "max": 38000, "currency": "GBP"},
        "skills": ["SQL", "Tableau", "Python"],
    },
)
add(
    "l2-job-03",
    2,
    "job_post",
    JOB_POST,
    J_INS,
    """
Orbit Robotics (Munich, Germany) seeks a Senior Embedded Engineer.
Salary: EUR 85,000 to EUR 100,000.
Tech: C++, RTOS, CAN bus.
""",
    {
        "title": "Senior Embedded Engineer",
        "company": {"name": "Orbit Robotics", "location": {"city": "Munich", "country": "Germany"}},
        "salary": {"min": 85000, "max": 100000, "currency": "EUR"},
        "skills": ["C++", "RTOS", "CAN bus"],
    },
)
add(
    "l2-job-04",
    2,
    "job_post",
    JOB_POST,
    J_INS,
    """
Product Designer | Lumen Health | Bengaluru, India
CTC: INR 18,00,000 - 24,00,000 (INR 1.8M - 2.4M)
Skills: Figma, user research, prototyping
""",
    {
        "title": "Product Designer",
        "company": {"name": "Lumen Health", "location": {"city": "Bengaluru", "country": "India"}},
        "salary": {"min": 1800000, "max": 2400000, "currency": "INR"},
        "skills": ["Figma", "user research", "prototyping"],
    },
)

O_INS = "Extract the order details from this confirmation email."
add(
    "l2-order-01",
    2,
    "order",
    ORDER,
    O_INS,
    """
Order confirmation - #A-55012
Hi Marcus Bell (marcus.bell@example.com), thanks for your order!
- SKU HD-2210 x 2 @ $14.99 each
- SKU CB-0087 x 1 @ $39.00 each
Ships to: 18 Elm Row, Portland, 97205
""",
    {
        "order_id": "A-55012",
        "customer": {"name": "Marcus Bell", "email": "marcus.bell@example.com"},
        "items": [
            {"sku": "HD-2210", "qty": 2, "unit_price": 14.99},
            {"sku": "CB-0087", "qty": 1, "unit_price": 39.00},
        ],
        "shipping_address": {"street": "18 Elm Row", "city": "Portland", "postal_code": "97205"},
    },
)
add(
    "l2-order-02",
    2,
    "order",
    ORDER,
    O_INS,
    """
Your order 99-3141 has been placed.
Customer: Aiko Tanaka <aiko.t@example.jp>
Items:
  1. TEA-SEN-100  qty 3  unit 8.50
  2. MUG-CER-02   qty 2  unit 12.00
  3. KETTLE-IRON  qty 1  unit 64.25
Delivery address: 2-11-3 Nishi-Azabu, Tokyo, 106-0031
""",
    {
        "order_id": "99-3141",
        "customer": {"name": "Aiko Tanaka", "email": "aiko.t@example.jp"},
        "items": [
            {"sku": "TEA-SEN-100", "qty": 3, "unit_price": 8.50},
            {"sku": "MUG-CER-02", "qty": 2, "unit_price": 12.00},
            {"sku": "KETTLE-IRON", "qty": 1, "unit_price": 64.25},
        ],
        "shipping_address": {
            "street": "2-11-3 Nishi-Azabu",
            "city": "Tokyo",
            "postal_code": "106-0031",
        },
    },
)
add(
    "l2-order-03",
    2,
    "order",
    ORDER,
    O_INS,
    """
Thanks, Sofia Martins! Order ref PT-7781 is on its way to Rua das Flores 72, Porto 4050-265.
You bought one BIKE-LOCK-U at 29.90 and four TUBE-700C at 6.50 each.
We'll email sofia.martins@example.pt when it ships.
""",
    {
        "order_id": "PT-7781",
        "customer": {"name": "Sofia Martins", "email": "sofia.martins@example.pt"},
        "items": [
            {"sku": "BIKE-LOCK-U", "qty": 1, "unit_price": 29.90},
            {"sku": "TUBE-700C", "qty": 4, "unit_price": 6.50},
        ],
        "shipping_address": {
            "street": "Rua das Flores 72",
            "city": "Porto",
            "postal_code": "4050-265",
        },
    },
)

# ---- Level 3
BR_INS = (
    "Triage this bug report. Priority is 1 (most urgent) to 5. "
    "estimated_hours is the engineer's estimate of the fix effort."
)
add(
    "l3-bug-01",
    3,
    "bug_report",
    BUG_REPORT,
    BR_INS,
    """
Title: Password reset link expires immediately
Reported against v3.8.2. Every reset email link returns "token expired" even when clicked
within seconds. I can reproduce this 100% of the time. Severity: HIGH. The auth team has
confirmed it. Assigned priority 2; Dana estimates about 6 hours to fix.
""",
    {
        "title": "Password reset link expires immediately",
        "severity": "high",
        "component": "auth",
        "status": "confirmed",
        "priority": 2,
        "reproducible": True,
        "affected_version": "3.8.2",
        "estimated_hours": 6,
    },
)
add(
    "l3-bug-02",
    3,
    "bug_report",
    BUG_REPORT,
    BR_INS,
    """
Title: Search results page shows duplicate items
Status: new. Version 2.1.0. Sometimes the search page returns the same product twice on page 1. We have not been able
to reproduce it reliably. Minor/low severity, cosmetic. Priority 4. Rough estimate: 3.5 hours.
""",
    {
        "title": "Search results page shows duplicate items",
        "severity": "low",
        "component": "search",
        "status": "new",
        "priority": 4,
        "reproducible": False,
        "affected_version": "2.1.0",
        "estimated_hours": 3.5,
    },
)
add(
    "l3-bug-03",
    3,
    "bug_report",
    BUG_REPORT,
    BR_INS,
    """
Invoices double-charged after retry
Version 5.0.0-rc1. When the payment gateway times out, our billing retry job charges the
customer a second time. Reproducible every time with the sandbox gateway. This is critical,
P1, and an engineer is already working on it (in progress). Estimate: 16 hours.
""",
    {
        "title": "Invoices double-charged after retry",
        "severity": "critical",
        "component": "billing",
        "status": "in_progress",
        "priority": 1,
        "reproducible": True,
        "affected_version": "5.0.0-rc1",
        "estimated_hours": 16,
    },
)
add(
    "l3-bug-04",
    3,
    "bug_report",
    BUG_REPORT,
    BR_INS,
    """
Dark mode toggle misaligned on settings page
Seen in 4.2.7. The toggle in the UI sits 3px below its label on Safari only. Reproducible
on every load. Medium severity. Product decided we won't fix this (wont_fix) because the
page is being redesigned. Priority 5, estimate 0.5 hours.
""",
    {
        "title": "Dark mode toggle misaligned on settings page",
        "severity": "medium",
        "component": "ui",
        "status": "wont_fix",
        "priority": 5,
        "reproducible": True,
        "affected_version": "4.2.7",
        "estimated_hours": 0.5,
    },
)

RV_INS = (
    "Analyse this product review. List each aspect the reviewer comments on, "
    "in order, with the reviewer's sentiment about it."
)
add(
    "l3-review-01",
    3,
    "review",
    REVIEW,
    RV_INS,
    """
Pixelon X5 phone - 4/5 stars. Paid $499.
The battery easily lasts two days, and the screen is gorgeous. Camera is just okay, nothing
special. Overall I'd recommend it to a friend, though it's not perfect.
""",
    {
        "product": "Pixelon X5",
        "rating": 4,
        "sentiment": "positive",
        "would_recommend": True,
        "price_paid": 499,
        "aspects": [
            {"aspect": "battery", "sentiment": "positive"},
            {"aspect": "screen", "sentiment": "positive"},
            {"aspect": "camera", "sentiment": "neutral"},
        ],
    },
)
add(
    "l3-review-02",
    3,
    "review",
    REVIEW,
    RV_INS,
    """
1 star for the AeroBook 14 laptop. I paid 899 dollars and the hinge cracked in week three -
the build quality is awful. Support never answered my emails. Do NOT buy this.
""",
    {
        "product": "AeroBook 14",
        "rating": 1,
        "sentiment": "negative",
        "would_recommend": False,
        "price_paid": 899,
        "aspects": [
            {"aspect": "build", "sentiment": "negative"},
            {"aspect": "support", "sentiment": "negative"},
        ],
    },
)
add(
    "l3-review-03",
    3,
    "review",
    REVIEW,
    RV_INS,
    """
Rating: 3 out of 5. SnapCam Mini, bought on sale for $79.99.
Great value for the price and the camera takes sharp photos, but the battery dies after an
hour. Mixed feelings; I wouldn't recommend it for travel.
""",
    {
        "product": "SnapCam Mini",
        "rating": 3,
        "sentiment": "mixed",
        "would_recommend": False,
        "price_paid": 79.99,
        "aspects": [
            {"aspect": "price", "sentiment": "positive"},
            {"aspect": "camera", "sentiment": "positive"},
            {"aspect": "battery", "sentiment": "negative"},
        ],
    },
)

F_INS = (
    "Extract the booking. Use 3-letter IATA airport codes. passengers counts all "
    "travellers; checked_bags is the total number of checked bags."
)
add(
    "l3-flight-01",
    3,
    "flight",
    FLIGHT,
    F_INS,
    """
Booking confirmed for Daniel Osei. Round trip, economy.
Outbound: London Heathrow (LHR) to Accra (ACC) on 2025-12-19.
Return: ACC to LHR on 2026-01-04.
1 passenger, 2 checked bags. Total fare: GBP 742.30.
""",
    {
        "passenger_name": "Daniel Osei",
        "trip_type": "round_trip",
        "cabin": "economy",
        "passengers": 1,
        "checked_bags": 2,
        "total_fare": 742.30,
        "segments": [
            {"from": "LHR", "to": "ACC", "date": "2025-12-19"},
            {"from": "ACC", "to": "LHR", "date": "2026-01-04"},
        ],
    },
)
add(
    "l3-flight-02",
    3,
    "flight",
    FLIGHT,
    F_INS,
    """
E-ticket: Lead passenger Maria Gonzalez + 2 children (3 travellers total).
One-way in Premium Economy from JFK to MAD, departing 14 July 2025.
No checked bags. Total charged: USD 2,985.00.
""",
    {
        "passenger_name": "Maria Gonzalez",
        "trip_type": "one_way",
        "cabin": "premium_economy",
        "passengers": 3,
        "checked_bags": 0,
        "total_fare": 2985.00,
        "segments": [{"from": "JFK", "to": "MAD", "date": "2025-07-14"}],
    },
)
add(
    "l3-flight-03",
    3,
    "flight",
    FLIGHT,
    F_INS,
    """
Itinerary for Wei Zhang, Business class, round trip.
SIN -> NRT, 3 March 2026; NRT -> SIN, 10 March 2026.
Travellers: 2. Bags: 1 checked per person. Fare total 4,120.50 SGD.
""",
    {
        "passenger_name": "Wei Zhang",
        "trip_type": "round_trip",
        "cabin": "business",
        "passengers": 2,
        "checked_bags": 2,
        "total_fare": 4120.50,
        "segments": [
            {"from": "SIN", "to": "NRT", "date": "2026-03-03"},
            {"from": "NRT", "to": "SIN", "date": "2026-03-10"},
        ],
    },
)

# ---- Level 4
IN_INS = (
    "Extract this incident report. The reporter's contact is either an email or a phone "
    "number. The resolution is either resolved (with root cause) or open."
)
add(
    "l4-incident-01",
    4,
    "incident",
    INCIDENT,
    IN_INS,
    """
Incident INC-4410, reported 2025-02-11 by Leo Park (leo.park@corp.example).
Impact: payments-api - outage (fully down for 40 minutes); checkout-web - degraded
(slow page loads). Status: resolved. Root cause: expired TLS certificate on the internal
load balancer. Fixed by: platform team.
""",
    {
        "incident": {
            "id": "INC-4410",
            "reported_at": "2025-02-11",
            "reporter": {
                "name": "Leo Park",
                "contact": {"kind": "email", "address": "leo.park@corp.example"},
            },
        },
        "systems": [
            {
                "name": "payments-api",
                "impact": {"level": "outage", "details": "fully down for 40 minutes"},
            },
            {"name": "checkout-web", "impact": {"level": "degraded", "details": "slow page loads"}},
        ],
        "resolution": {
            "status": "resolved",
            "root_cause": "expired TLS certificate on the internal load balancer",
            "fixed_by": "platform team",
        },
    },
)
add(
    "l4-incident-02",
    4,
    "incident",
    INCIDENT,
    IN_INS,
    """
INC-4502 | 2025-05-30 | Reporter: Amara Nwosu, phone +234 803 555 0100
search-indexer: degraded.
Still open - engineers expect a fix within 12 hours.
Note: customers were notified via the status page.
""",
    {
        "incident": {
            "id": "INC-4502",
            "reported_at": "2025-05-30",
            "reporter": {
                "name": "Amara Nwosu",
                "contact": {"kind": "phone", "number": "+234 803 555 0100"},
            },
        },
        "systems": [{"name": "search-indexer", "impact": {"level": "degraded"}}],
        "resolution": {"status": "open", "eta_hours": 12},
        "notes": "customers were notified via the status page",
    },
)
add(
    "l4-incident-03",
    4,
    "incident",
    INCIDENT,
    IN_INS,
    """
Report INC-4611 filed on 2025-08-03 by Jonas Berg (jonas.berg@corp.example).
Systems checked: auth-service (no impact), billing-worker (outage: jobs stuck in queue),
reports-ui (degraded).
Resolved. Root cause: bad config push to the queue broker.
""",
    {
        "incident": {
            "id": "INC-4611",
            "reported_at": "2025-08-03",
            "reporter": {
                "name": "Jonas Berg",
                "contact": {"kind": "email", "address": "jonas.berg@corp.example"},
            },
        },
        "systems": [
            {"name": "auth-service", "impact": {"level": "none"}},
            {
                "name": "billing-worker",
                "impact": {"level": "outage", "details": "jobs stuck in queue"},
            },
            {"name": "reports-ui", "impact": {"level": "degraded"}},
        ],
        "resolution": {"status": "resolved", "root_cause": "bad config push to the queue broker"},
    },
)
add(
    "l4-incident-04",
    4,
    "incident",
    INCIDENT,
    IN_INS,
    """
INC-4700 opened 2025-10-21. Reported by phone by Chen Li (+86 21 5555 0123).
The mobile-gateway is in full outage. Investigation ongoing, no ETA yet.
""",
    {
        "incident": {
            "id": "INC-4700",
            "reported_at": "2025-10-21",
            "reporter": {
                "name": "Chen Li",
                "contact": {"kind": "phone", "number": "+86 21 5555 0123"},
            },
        },
        "systems": [{"name": "mobile-gateway", "impact": {"level": "outage"}}],
        "resolution": {"status": "open"},
    },
)

T_INS = (
    "Extract this payment record. The payment method is a card, a bank transfer, or cash. "
    "Shipping is optional; include it only if the text describes shipping."
)
add(
    "l4-payment-01",
    4,
    "transaction",
    TRANSACTION,
    T_INS,
    """
Receipt - paid by Olivia Grant with a Visa card ending 4821.
Items: Wool scarf 45.00 (10% member discount: 4.50 off); Leather gloves 60.00.
Shipped with DHL to 9 Queen's Road, Edinburgh, United Kingdom.
""",
    {
        "payer": {
            "name": "Olivia Grant",
            "method": {"kind": "card", "brand": "Visa", "last4": "4821"},
        },
        "line_items": [
            {"description": "Wool scarf", "amount": 45.00, "discount": 4.50},
            {"description": "Leather gloves", "amount": 60.00},
        ],
        "shipping": {
            "carrier": "DHL",
            "address": {
                "street": "9 Queen's Road",
                "city": "Edinburgh",
                "country": "United Kingdom",
            },
        },
    },
)
add(
    "l4-payment-02",
    4,
    "transaction",
    TRANSACTION,
    T_INS,
    """
Payment received from Rahul Mehta by bank transfer (HDFC Bank, ref UTR-88213407).
Covers: Annual software licence 1200.00; Onboarding workshop 300.00.
Digital delivery only - nothing shipped.
""",
    {
        "payer": {
            "name": "Rahul Mehta",
            "method": {"kind": "bank_transfer", "bank": "HDFC Bank", "reference": "UTR-88213407"},
        },
        "line_items": [
            {"description": "Annual software licence", "amount": 1200.00},
            {"description": "Onboarding workshop", "amount": 300.00},
        ],
    },
)
add(
    "l4-payment-03",
    4,
    "transaction",
    TRANSACTION,
    T_INS,
    """
Farmers' market stall sale. Customer: Grace Kim, paid cash.
Honey jar 12.00, beeswax candle 8.00, bread loaf 6.50 with 1.00 off.
""",
    {
        "payer": {"name": "Grace Kim", "method": {"kind": "cash"}},
        "line_items": [
            {"description": "Honey jar", "amount": 12.00},
            {"description": "beeswax candle", "amount": 8.00},
            {"description": "bread loaf", "amount": 6.50, "discount": 1.00},
        ],
    },
)

SC_INS = (
    "Extract the conference schedule. Day is the conference day number (1-3). "
    "speaker is null for sessions without a named speaker."
)
add(
    "l4-schedule-01",
    4,
    "schedule",
    SCHEDULE,
    SC_INS,
    """
DataFest 2025 - Day 1
09:00 Opening remarks - no speaker listed - Main Hall
09:30 "Vector Search in Practice" - Ines Duarte (University of Coimbra) - Room B
Day 2
14:00 "Lessons from 10 Years of Airflow" - Sam Whitaker
""",
    {
        "event": "DataFest 2025",
        "sessions": [
            {
                "title": "Opening remarks",
                "speaker": None,
                "slot": {"day": 1, "start": "09:00"},
                "room": "Main Hall",
            },
            {
                "title": "Vector Search in Practice",
                "speaker": {"name": "Ines Duarte", "affiliation": "University of Coimbra"},
                "slot": {"day": 1, "start": "09:30"},
                "room": "Room B",
            },
            {
                "title": "Lessons from 10 Years of Airflow",
                "speaker": {"name": "Sam Whitaker"},
                "slot": {"day": 2, "start": "14:00"},
            },
        ],
    },
)
add(
    "l4-schedule-02",
    4,
    "schedule",
    SCHEDULE,
    SC_INS,
    """
RustConf Asia programme.
Day 3, 11:15 - keynote "Async Rust, Five Years On" by Mei Takahashi (Ferrous Labs), Auditorium.
Day 3, 16:30 - Closing panel (moderated by the organisers, no individual speaker), Auditorium.
""",
    {
        "event": "RustConf Asia",
        "sessions": [
            {
                "title": "Async Rust, Five Years On",
                "speaker": {"name": "Mei Takahashi", "affiliation": "Ferrous Labs"},
                "slot": {"day": 3, "start": "11:15"},
                "room": "Auditorium",
            },
            {
                "title": "Closing panel",
                "speaker": None,
                "slot": {"day": 3, "start": "16:30"},
                "room": "Auditorium",
            },
        ],
    },
)
add(
    "l4-schedule-03",
    4,
    "schedule",
    SCHEDULE,
    SC_INS,
    """
GreenBuild Summit
Day 2 - 10:00 - "Mass Timber at Scale" with architect Lars Nilsson (Nordic Timber Studio), Hall 3
Day 2 - 13:30 - Networking lunch
Day 2 - 15:00 - "Retrofits That Pay Back" - Priya Nair, Hall 1
""",
    {
        "event": "GreenBuild Summit",
        "sessions": [
            {
                "title": "Mass Timber at Scale",
                "speaker": {"name": "Lars Nilsson", "affiliation": "Nordic Timber Studio"},
                "slot": {"day": 2, "start": "10:00"},
                "room": "Hall 3",
            },
            {"title": "Networking lunch", "speaker": None, "slot": {"day": 2, "start": "13:30"}},
            {
                "title": "Retrofits That Pay Back",
                "speaker": {"name": "Priya Nair"},
                "slot": {"day": 2, "start": "15:00"},
                "room": "Hall 1",
            },
        ],
    },
)


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "data" / "tasks.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for t in TASKS:
            fh.write(json.dumps(t, ensure_ascii=False) + "\n")
    counts = {lvl: sum(t["difficulty"] == lvl for t in TASKS) for lvl in (1, 2, 3, 4)}
    print(f"wrote {len(TASKS)} tasks to {out}: {counts}")


if __name__ == "__main__":
    main()
