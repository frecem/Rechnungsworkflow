from datetime import date, timedelta
from decimal import Decimal

from app.models import Invoice
from app.services.stats import NO_CATEGORY_LABEL, available_years, compute_yearly_stats, recurring_overview


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


def test_compute_yearly_stats_category_filter():
    invoices = [
        _invoice(hash="a", category="Büro", amount_gross=Decimal("30.00")),
        _invoice(hash="b", category="Software", amount_gross=Decimal("80.00")),
    ]
    stats = compute_yearly_stats(invoices, 2026, category="Software")
    assert stats.invoice_count == 1
    assert stats.total_gross == Decimal("80.00")


def test_compute_yearly_stats_category_filter_no_category_bucket():
    invoices = [
        _invoice(hash="a", category=None, amount_gross=Decimal("30.00")),
        _invoice(hash="b", category="Software", amount_gross=Decimal("80.00")),
    ]
    stats = compute_yearly_stats(invoices, 2026, category=NO_CATEGORY_LABEL)
    assert stats.invoice_count == 1
    assert stats.total_gross == Decimal("30.00")


def test_recurring_overview_groups_by_sender():
    invoices = [
        _invoice(hash="a", sender_name="Vermieter GmbH", is_recurring=True, recurrence_interval_days=30,
                 invoice_date=date(2026, 1, 1), amount_gross=Decimal("800.00")),
        _invoice(hash="b", sender_name="Vermieter GmbH", is_recurring=True, recurrence_interval_days=30,
                 invoice_date=date(2026, 2, 1), amount_gross=Decimal("800.00")),
        _invoice(hash="c", sender_name="Netflix", is_recurring=True, recurrence_interval_days=30,
                 invoice_date=date(2026, 1, 15), amount_gross=Decimal("15.00")),
        _invoice(hash="d", sender_name="Einmalig GmbH", is_recurring=False, amount_gross=Decimal("50.00")),
    ]
    groups = recurring_overview(invoices, today=date(2026, 2, 5))
    labels = {g.label: g for g in groups}
    assert "Einmalig GmbH" not in labels
    assert labels["Vermieter GmbH"].count == 2
    assert labels["Vermieter GmbH"].total == Decimal("1600.00")
    assert labels["Vermieter GmbH"].last_date == date(2026, 2, 1)
    assert labels["Netflix"].count == 1


def test_recurring_overview_marks_overdue_when_expected_date_passed():
    invoices = [
        _invoice(hash="a", sender_name="Netflix", is_recurring=True, recurrence_interval_days=30,
                 invoice_date=date(2026, 1, 1), amount_gross=Decimal("15.00")),
    ]
    # 30 Tage Intervall + 7 Tage Kulanz = ueberfaellig ab 2026-02-08
    not_yet = recurring_overview(invoices, today=date(2026, 2, 7))
    assert not_yet[0].is_overdue is False

    overdue = recurring_overview(invoices, today=date(2026, 2, 9))
    assert overdue[0].is_overdue is True
    assert overdue[0].expected_next == date(2026, 1, 31)


def test_recurring_overview_ended_series_never_overdue():
    invoices = [
        _invoice(hash="a", sender_name="Netflix", is_recurring=True, recurrence_interval_days=30,
                 invoice_date=date(2026, 1, 1), amount_gross=Decimal("15.00"), recurring_ended=True),
    ]
    groups = recurring_overview(invoices, today=date(2026, 6, 1))
    assert groups[0].is_ended is True
    assert groups[0].is_overdue is False
    assert groups[0].expected_next is None


def test_recurring_overview_latest_invoice_id_used_for_ended_flag():
    inv1 = _invoice(hash="a", sender_name="Netflix", is_recurring=True, recurrence_interval_days=30,
                     invoice_date=date(2026, 1, 1), recurring_ended=True)
    inv2 = _invoice(hash="b", sender_name="Netflix", is_recurring=True, recurrence_interval_days=30,
                     invoice_date=date(2026, 3, 1), recurring_ended=False)
    groups = recurring_overview([inv1, inv2], today=date(2026, 6, 1))
    # Die neuere Rechnung (b) ohne recurring_ended bestimmt die aktuelle Ueberfaelligkeit,
    # nicht die aeltere, bereits als beendet markierte Rechnung
    assert groups[0].is_ended is False
    assert groups[0].is_overdue is True


def test_recurring_overview_without_interval_has_no_expected_next():
    invoices = [
        _invoice(hash="a", sender_name="Netflix", is_recurring=True, recurrence_interval_days=None,
                 invoice_date=date(2026, 1, 1)),
    ]
    groups = recurring_overview(invoices, today=date(2026, 6, 1))
    assert groups[0].expected_next is None
    assert groups[0].is_overdue is False
