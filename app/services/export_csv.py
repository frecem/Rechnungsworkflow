import csv
import io
from collections.abc import Iterable

from app.models import Invoice

# Zeichen, mit denen Excel/LibreOffice eine Zelle als Formel interpretieren.
# Betroffene Felder (z.B. sender_name) stammen aus der OCR fremder Rechnungen und
# sind damit von aussen beeinflussbar - ohne Entschaerfung koennte eine praeparierte
# Rechnung beim Oeffnen des Exports Code ausfuehren (CSV-/Formel-Injection).
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

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
                _escape_formula(invoice.sender_name),
                _escape_formula(invoice.invoice_number),
                _fmt_decimal(invoice.amount_net),
                _fmt_decimal(invoice.vat_amount),
                _fmt_decimal(invoice.vat_rate),
                _fmt_decimal(invoice.amount_gross),
                _escape_formula(invoice.currency),
                _escape_formula(invoice.category),
                invoice.status,
                invoice.source_type,
                _escape_formula(invoice.file_path),
            ]
        )

    return buffer.getvalue()


def _escape_formula(value: str | None) -> str:
    """Stellt einer als Formel interpretierbaren Zelle ein ' voran (Excel-Konvention).

    Der Text bleibt dabei unveraendert lesbar, wird aber garantiert als Text und
    nicht als Formel ausgewertet.
    """
    text = value or ""
    if text.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def _fmt_decimal(value) -> str:
    if value is None:
        return ""
    return str(value).replace(".", ",")
