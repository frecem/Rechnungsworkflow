"""Jahres-/Kategorie-Auswertung für einen schnellen Überblick vor der Steuererklärung.

Zählt alle Rechnungen außer abgelehnten (`rejected`) mit, auch solche, die noch nicht
final freigegeben sind - fuer einen vollstaendigen Ueberblick. Gruppiert nach
`invoice_date` (nicht `due_date`), da das dem tatsaechlichen Ausgabezeitpunkt entspricht.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.models import Invoice

RECURRING_ALERT_GRACE_DAYS = 7

NO_CATEGORY_LABEL = "– keine Kategorie –"
MONTH_NAMES = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


@dataclass
class GroupTotal:
    label: str
    total: Decimal
    count: int


@dataclass
class YearlyStats:
    year: int
    invoice_count: int
    total_gross: Decimal
    total_net: Decimal
    total_vat: Decimal
    by_category: list[GroupTotal] = field(default_factory=list)
    by_month: list[GroupTotal] = field(default_factory=list)


def available_years(invoices: list[Invoice]) -> list[int]:
    years = {inv.invoice_date.year for inv in invoices if inv.invoice_date}
    return sorted(years, reverse=True)


def compute_yearly_stats(invoices: list[Invoice], year: int, category: str | None = None) -> YearlyStats:
    relevant = [inv for inv in invoices if inv.status != "rejected" and inv.invoice_date and inv.invoice_date.year == year]
    if category:
        relevant = [inv for inv in relevant if (inv.category or NO_CATEGORY_LABEL) == category]

    total_gross = sum((inv.amount_gross or Decimal("0") for inv in relevant), Decimal("0"))
    total_net = sum((inv.amount_net or Decimal("0") for inv in relevant), Decimal("0"))
    total_vat = sum((inv.vat_amount or Decimal("0") for inv in relevant), Decimal("0"))

    category_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    category_counts: dict[str, int] = defaultdict(int)
    for inv in relevant:
        label = inv.category or NO_CATEGORY_LABEL
        category_totals[label] += inv.amount_gross or Decimal("0")
        category_counts[label] += 1

    by_category = sorted(
        (GroupTotal(label=label, total=total, count=category_counts[label]) for label, total in category_totals.items()),
        key=lambda g: g.total,
        reverse=True,
    )

    month_totals: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    month_counts: dict[int, int] = defaultdict(int)
    for inv in relevant:
        month = inv.invoice_date.month
        month_totals[month] += inv.amount_gross or Decimal("0")
        month_counts[month] += 1

    by_month = [
        GroupTotal(label=MONTH_NAMES[m - 1], total=month_totals[m], count=month_counts[m])
        for m in range(1, 13)
        if m in month_totals
    ]

    return YearlyStats(
        year=year,
        invoice_count=len(relevant),
        total_gross=total_gross,
        total_net=total_net,
        total_vat=total_vat,
        by_category=by_category,
        by_month=by_month,
    )


@dataclass
class RecurringGroup:
    label: str
    count: int
    total: Decimal
    interval_days: int | None
    last_date: date
    expected_next: date | None
    is_overdue: bool = False


def recurring_overview(invoices: list[Invoice], today: date | None = None) -> list[RecurringGroup]:
    """Gruppiert als wiederkehrend markierte Rechnungen nach Absender.

    `expected_next` wird aus dem Intervall der zuletzt eingegangenen Rechnung der
    Gruppe berechnet; `is_overdue` ist gesetzt, wenn dieser Termin (plus
    Kulanzfrist) bereits verstrichen ist, ohne dass eine neue Rechnung eingetroffen ist.
    """
    today = today or date.today()
    recurring = [inv for inv in invoices if inv.is_recurring and inv.invoice_date]

    groups: dict[str, list[Invoice]] = defaultdict(list)
    for inv in recurring:
        groups[inv.sender_name or "Unbekannt"].append(inv)

    result = []
    for label, invs in groups.items():
        invs_sorted = sorted(invs, key=lambda i: i.invoice_date)
        latest = invs_sorted[-1]
        total = sum((i.amount_gross or Decimal("0") for i in invs), Decimal("0"))

        expected_next = None
        is_overdue = False
        if latest.recurrence_interval_days:
            expected_next = latest.invoice_date + timedelta(days=latest.recurrence_interval_days)
            is_overdue = today > expected_next + timedelta(days=RECURRING_ALERT_GRACE_DAYS)

        result.append(
            RecurringGroup(
                label=label,
                count=len(invs),
                total=total,
                interval_days=latest.recurrence_interval_days,
                last_date=latest.invoice_date,
                expected_next=expected_next,
                is_overdue=is_overdue,
            )
        )

    return sorted(result, key=lambda g: g.label)
