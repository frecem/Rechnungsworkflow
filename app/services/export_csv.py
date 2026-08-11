import csv
import io
from collections.abc import Iterable

from app.models import Invoice

CSV_COLUMNS = [
    "id",
    "invoice_date",
    "sender_name",
    "invoice_number",
    "amount_net",
    "vat_amount",
    "vat_rate",
    "amount_gross",
    "currency",
    "category",
    "status",
    "source_type",
    "file_path",
]


def build_csv(invoices: Iterable[Invoice]) -> str:
    """Baut einen generischen CSV-String aus gefilterten Rechnungen.

    Bewusst als flache Spaltenliste gehalten (Netto/USt/Brutto getrennt), damit ein
    spaeterer DATEV-Export dieselbe gefilterte Query wiederverwenden und die Spalten
    nur umformen muss, ohne diese Funktion oder das Datenmodell anzufassen.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(CSV_COLUMNS)

    for invoice in invoices:
        writer.writerow(
            [
                invoice.id,
                invoice.invoice_date.isoformat() if invoice.invoice_date else "",
                invoice.sender_name or "",
                invoice.invoice_number or "",
                _fmt_decimal(invoice.amount_net),
                _fmt_decimal(invoice.vat_amount),
                _fmt_decimal(invoice.vat_rate),
                _fmt_decimal(invoice.amount_gross),
                invoice.currency,
                invoice.category or "",
                invoice.status,
                invoice.source_type,
                invoice.file_path,
            ]
        )

    return buffer.getvalue()


def _fmt_decimal(value) -> str:
    if value is None:
        return ""
    return str(value).replace(".", ",")
