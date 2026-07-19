# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""Cadence — a small, doctype-agnostic recurrence engine.

The rhythm at which *anything* recurs — a daily SOP, a monthly GST return, a
quarterly KPI review, an annual licence renewal. Every recurring thing has a
``cadence``; where the exact dates matter, it also carries a **Cadence Schedule**:
a flat list where each row is ONE occurrence per fiscal year, spelling out its
own period and its own due date.

This module is pure Python (stdlib only) so it can be reasoned about and tested
in isolation — no Frappe, no DB. Callers (Compliance Return Definition, HRMS
Task, or anything future) pass in the schedule rows + a fiscal-year anchor and
get back resolved ``(label, period_start, period_end, due_date)`` occurrences.

Everything is anchored to the **Indian fiscal year** (1 April – 31 March). A
``fy_start_year`` of 2026 means FY 2026-27. Each date on a row is a
``(month, year_index)`` pair, where ``year_index`` is the offset in whole years
from ``fy_start_year`` (0 = same year, 1 = next, 2 = the year after). That single
idea makes every wrap unambiguous — Jan–Mar periods, GST dues in the *next*
month, and an annual return due in December of the *following* year all fall out
of the same arithmetic, with no special cases in the resolver.
"""

from calendar import monthrange
from datetime import date

# Cadences that carry an explicit per-occurrence schedule. Daily / Weekly /
# On-demand don't — they either fire every day or are triggered by hand, so a
# month/day table would be meaningless for them.
SCHEDULED_CADENCES = ("Monthly", "Quarterly", "Half-Yearly", "Annually")

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)

# ``due_day`` sentinel: fall on the last calendar day of ``due_month`` (handles
# 28/29/30/31 automatically). Also used whenever a supplied day overflows the
# month, so "31" quietly becomes "30"/"28" where needed.
LAST_DAY = 0


def _month_num(value) -> int:
    """Accept a month as an int (1-12) or a name ('April' / 'Apr')."""
    if isinstance(value, int):
        return value
    if value is None:
        raise ValueError("month is required")
    s = str(value).strip()
    if s.isdigit():
        return int(s)
    s_low = s.lower()
    for i, name in enumerate(MONTHS, start=1):
        if name.lower() == s_low or name.lower().startswith(s_low[:3]):
            return i
    raise ValueError(f"unrecognised month: {value!r}")


def _clamped_day(year: int, month: int, day) -> int:
    """Clamp ``day`` into a valid day for (year, month). ``LAST_DAY`` (0), None,
    or any overflow (e.g. 31 in a 30-day month) collapse to the month's end."""
    last = monthrange(year, month)[1]
    if day in (None, LAST_DAY, "", "0"):
        return last
    d = int(day)
    if d < 1:
        return last
    return min(d, last)


def _row(row, key, default=None):
    """Read ``key`` from a row that may be a dict or an object (a Frappe child
    doc). Keeps the engine indifferent to how the caller stores rows."""
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def resolve_occurrence(row, fy_start_year: int) -> dict:
    """Resolve ONE Cadence Schedule row into absolute dates for the given FY.

    Returns ``{label, period_start, period_end, due_date}`` (dates are
    ``datetime.date``). Raises ``ValueError`` on an unusable row so a caller can
    skip-and-log rather than emit a wrong date silently.
    """
    label = (_row(row, "occurrence_label") or "").strip()
    if not label:
        raise ValueError("occurrence_label is required")

    psm = _month_num(_row(row, "period_start_month"))
    pem = _month_num(_row(row, "period_end_month"))
    dm = _month_num(_row(row, "due_month"))

    psy = fy_start_year + int(_row(row, "period_start_year_index", 0) or 0)
    pey = fy_start_year + int(_row(row, "period_end_year_index", 0) or 0)
    dy = fy_start_year + int(_row(row, "due_year_index", 0) or 0)

    period_start = date(psy, psm, 1)
    period_end = date(pey, pem, monthrange(pey, pem)[1])
    due_date = date(dy, dm, _clamped_day(dy, dm, _row(row, "due_day")))

    if period_end < period_start:
        raise ValueError(
            f"{label}: resolved period end {period_end} precedes start {period_start} "
            "(check the year offsets)"
        )

    return {
        "label": label,
        "period_start": period_start,
        "period_end": period_end,
        "due_date": due_date,
    }


def resolve_schedule(rows, fy_start_year: int) -> list[dict]:
    """Resolve all ACTIVE rows for a FY, sorted by due date.

    Skips rows flagged inactive and rows that don't resolve, so one malformed
    row never poisons the whole schedule. Callers that want strictness can call
    ``resolve_occurrence`` per row instead.
    """
    out = []
    for row in rows or []:
        active = _row(row, "active", 1)
        if active in (0, "0", False):
            continue
        try:
            out.append(resolve_occurrence(row, fy_start_year))
        except (ValueError, TypeError):
            # Malformed row — the caller logs; the engine stays pure.
            continue
    out.sort(key=lambda o: o["due_date"])
    return out


# ---------------------------------------------------------------------------
# Fiscal-year helpers
# ---------------------------------------------------------------------------


def fy_start_year_for(d: date) -> int:
    """The April-1 year of the Indian FY containing ``d`` (Jan-Mar → prior year)."""
    return d.year if d.month >= 4 else d.year - 1


def fy_label(fy_start_year: int) -> str:
    """'FY 2026-27' for a start year of 2026."""
    return f"FY {fy_start_year}-{str(fy_start_year + 1)[-2:]}"


# ---------------------------------------------------------------------------
# The smart generator — turn a plain cadence + a due rule into explicit rows
# ---------------------------------------------------------------------------

# FY runs April(ordinal 0) .. March(ordinal 11). These two helpers convert
# between a calendar month and its position in the FY, so month-arithmetic that
# wraps past March into the next year Just Works.


def _cal_to_ordinal(month: int) -> int:
    return (month - 4) % 12


def _ordinal_to_month_yi(ordinal: int) -> tuple[int, int]:
    """FY ordinal (0=Apr, can exceed 11 into next year) -> (calendar_month, year_index)."""
    return (((ordinal + 3) % 12) + 1, (ordinal + 3) // 12)


def generate_rows(
    cadence: str,
    due_day=LAST_DAY,
    due_month_offset: int = 1,
    months: list | None = None,
    label_prefix: str = "",
) -> list[dict]:
    """Produce a starter set of Cadence Schedule rows for a standard cadence.

    A convenience so an author rarely hand-types the year offsets. The returned
    rows are the source of truth thereafter — irregular real-world dates (e.g.
    TDS Q4 falling on 31 May instead of 30 Apr) are then tweaked on the one row
    that differs.

    - ``due_day``      : day the filing is due (``LAST_DAY``/0 = month end)
    - ``due_month_offset`` : whole months AFTER the period end that the due date
      sits in (GST → 1 = next month; a same-period due → 0)
    - ``months``       : for Monthly, restrict to these calendar months (1-12);
      default = all twelve
    - ``label_prefix`` : prepended to each occurrence_label (e.g. 'GSTR3B-')
    """
    cadence = (cadence or "").strip()
    if cadence not in SCHEDULED_CADENCES:
        return []

    if cadence == "Monthly":
        period_spans = [(m, m) for m in (months or list(range(1, 13)))]
    elif cadence == "Quarterly":
        period_spans = [(4, 6), (7, 9), (10, 12), (1, 3)]
    elif cadence == "Half-Yearly":
        period_spans = [(4, 9), (10, 3)]
    else:  # Annually
        period_spans = [(4, 3)]

    rows = []
    for idx, (start_m, end_m) in enumerate(period_spans, start=1):
        start_ord = _cal_to_ordinal(start_m)
        end_ord = _cal_to_ordinal(end_m)
        # Half-Yearly / Annual spans wrap (e.g. Oct->Mar): keep end after start.
        if end_ord < start_ord:
            end_ord += 12
        _, psy = _ordinal_to_month_yi(start_ord)
        _, pey = _ordinal_to_month_yi(end_ord)
        due_ord = end_ord + int(due_month_offset)
        due_m, dyi = _ordinal_to_month_yi(due_ord)

        label = _default_label(cadence, start_m, end_m, idx)
        rows.append(
            {
                "occurrence_label": f"{label_prefix}{label}",
                "period_start_month": MONTHS[start_m - 1],
                "period_start_year_index": psy,
                "period_end_month": MONTHS[end_m - 1],
                "period_end_year_index": pey,
                "due_month": MONTHS[due_m - 1],
                "due_day": due_day,
                "due_year_index": dyi,
                "active": 1,
            }
        )
    return rows


def _default_label(cadence: str, start_m: int, end_m: int, idx: int) -> str:
    if cadence == "Monthly":
        return MONTHS[start_m - 1][:3]
    if cadence == "Quarterly":
        return f"Q{idx}"
    if cadence == "Half-Yearly":
        return "H1" if idx == 1 else "H2"
    return "Annual"


def next_due(rows, on_date: date, fy_start_year: int | None = None) -> dict | None:
    """The soonest occurrence due on/after ``on_date`` (looks into next FY too).

    Handy for a 'what's next' preview without materialising a whole calendar.
    """
    for fy in (
        [fy_start_year] if fy_start_year is not None
        else [fy_start_year_for(on_date), fy_start_year_for(on_date) + 1]
    ):
        for occ in resolve_schedule(rows, fy):
            if occ["due_date"] >= on_date:
                return occ
    return None
