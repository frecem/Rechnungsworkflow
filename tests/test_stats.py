from datetime import date
from decimal import Decimal

from app.models import Invoice
from app.services.stats import NO_CATEGORY_LABEL, available_years, compute_yearly_stats


def _invoice(**overrides):
    defaults = dict(
        source_type="upload",
        file_path="x",
        file_hash_sha256=overrides.pop("hash", "h"),
        status="approved",
        invoice_date=date(2026, 1, 1),
        amount_gross=Decimal("100.00"),
        amount_net=Decimal("84.03"),
        vat_amount=Decimal("15.97"),
        currency="EUR",
        category="Büro",
    )
    defaults.update(overrides)
    return Invoice(**defaults)


def test_available_years_sorted_descending():
    invoices = [
        _invoice(hash="a", invoice_date=date(2025, 3, 1)),
        _invoice(hash="b", invoice_date=date(2026, 1, 1)),
        _invoice(hash="c", invoice_date=date(2024, 6, 1)),
        _invoice(hash="d", invoice_date=None),
    ]
    assert available_years(invoices) == [2026, 2025, 2024]


def test_compute_yearly_stats_totals():
    invoices = [
        _invoice(hash="a", invoice_date=date(2026, 1, 5), amount_gross=Decimal("100.00")),
        _invoice(hash="b", invoice_date=date(2026, 2, 10), amount_gross=Decimal("50.00")),
        _invoice(hash="c", invoice_date=date(2025, 1, 1), amount_gross=Decimal("999.00")),
    ]
    stats = compute_yearly_stats(invoices, 2026)
    assert stats.invoice_count == 2
    assert stats.total_gross == Decimal("150.00")


def test_compute_yearly_stats_excludes_rejected():
    invoices = [
        _invoice(hash="a", status="approved", amount_gross=Decimal("100.00")),
        _invoice(hash="b", status="rejected", amount_gross=Decimal("500.00")),
    ]
    stats = compute_yearly_stats(invoices, 2026)
    assert stats.invoice_count == 1
    assert stats.total_gross == Decimal("100.00")


def test_compute_yearly_stats_by_category():
    invoices = [
        _invoice(hash="a", category="Büro", amount_gross=Decimal("30.00")),
        _invoice(hash="b", category="Büro", amount_gross=Decimal("20.00")),
        _invoice(hash="c", category="Software", amount_gross=Decimal("80.00")),
        _invoice(hash="d", category=None, amount_gross=Decimal("10.00")),
    ]
    stats = compute_yearly_stats(invoices, 2026)
    labels_totals = {row.label: row.total for row in stats.by_category}
    assert labels_totals["Büro"] == Decimal("50.00")
    assert labels_totals["Software"] == Decimal("80.00")
    assert labels_totals[NO_CATEGORY_LABEL] == Decimal("10.00")
    # sortiert nach Summe absteigend
    assert stats.by_category[0].label == "Software"


def test_compute_yearly_stats_by_month_only_includes_months_with_data():
    invoices = [
        _invoice(hash="a", invoice_date=date(2026, 1, 5), amount_gross=Decimal("10.00")),
        _invoice(hash="b", invoice_date=date(2026, 3, 5), amount_gross=Decimal("20.00")),
    ]
    stats = compute_yearly_stats(invoices, 2026)
    assert [row.label for row in stats.by_month] == ["Januar", "März"]


def test_compute_yearly_stats_empty_year():
    stats = compute_yearly_stats([], 2026)
    assert stats.invoice_count == 0
    assert stats.total_gross == Decimal("0")
    assert stats.by_category == []
    assert stats.by_month == []
