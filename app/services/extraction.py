"""Regex-basierte Heuristiken, um aus rohem OCR-/PDF-Text Rechnungsfelder zu erraten.

Alle Funktionen geben lieber `None` zurueck als einen falschen Wert zu raten - die
extrahierten Felder werden im UI ohnehin immer als editierbarer Vorschlag angezeigt,
den der Nutzer vor der Freigabe prueft.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from dateutil import parser as date_parser

_AMOUNT_NUMBER = r"(\d{1,3}(?:[.\s]\d{3})*,\d{2}|\d+\.\d{2})"

_GROSS_KEYWORDS = [
    "Gesamtbetrag", "Rechnungsbetrag", "Endbetrag", "Zu zahlen", "Gesamtsumme",
    "Summe", "Total", "Betrag",
]
_NET_KEYWORDS = ["Nettobetrag", "Netto", "Zwischensumme"]
_VAT_KEYWORDS = ["MwSt", "USt", "Umsatzsteuer", "Mehrwertsteuer"]
_INVOICE_NUMBER_KEYWORDS = [
    "Rechnungsnummer", "Rechnungs-Nr", "Rechnung Nr", "Rechnungsnr", "Invoice No",
    "Invoice Number", "Belegnummer", "Beleg-Nr",
]
_DATE_KEYWORDS = ["Rechnungsdatum", "Datum", "Invoice Date", "Belegdatum"]

_DATE_PATTERN = re.compile(r"\b(\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d{4}-\d{2}-\d{2})\b")
_VAT_RATE_PATTERN = re.compile(r"(\d{1,2}(?:[,.]\d+)?)\s?%")

_IBAN_PATTERN = re.compile(r"\b([A-Z]{2}\d{2}(?:\s?[A-Z0-9]{1,4}){2,7})\b")
_BIC_KEYWORDS = ["BIC", "SWIFT"]


@dataclass
class ExtractedFields:
    sender_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    amount_gross: Decimal | None = None
    amount_net: Decimal | None = None
    vat_amount: Decimal | None = None
    vat_rate: Decimal | None = None
    sender_low_confidence: bool = True


def parse_de_amount(raw: str) -> Decimal | None:
    """Wandelt '1.234,56' oder '1234.56' in Decimal('1234.56') um."""
    raw = raw.strip()
    if not raw:
        return None
    if "," in raw:
        raw = raw.replace(".", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _find_amount_near_keywords(text: str, keywords: list[str]) -> Decimal | None:
    for keyword in keywords:
        pattern = re.compile(
            rf"{re.escape(keyword)}[^\n]{{0,25}}?{_AMOUNT_NUMBER}", re.IGNORECASE
        )
        match = pattern.search(text)
        if match:
            amount = parse_de_amount(match.group(1))
            if amount is not None:
                return amount
    return None


def _find_largest_amount(text: str) -> Decimal | None:
    amounts = [parse_de_amount(m) for m in re.findall(_AMOUNT_NUMBER, text)]
    amounts = [a for a in amounts if a is not None]
    return max(amounts) if amounts else None


def _extract_amounts(text: str) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
    gross = _find_amount_near_keywords(text, _GROSS_KEYWORDS)
    net = _find_amount_near_keywords(text, _NET_KEYWORDS)
    vat_amount = _find_amount_near_keywords(text, _VAT_KEYWORDS)

    vat_rate = None
    rate_match = _VAT_RATE_PATTERN.search(text)
    if rate_match:
        vat_rate = parse_de_amount(rate_match.group(1)) or _try_plain_decimal(rate_match.group(1))

    if gross is None:
        gross = _find_largest_amount(text)

    return gross, net, vat_amount, vat_rate


def _try_plain_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "."))
    except InvalidOperation:
        return None


def _extract_date(text: str) -> date | None:
    for keyword in _DATE_KEYWORDS:
        pattern = re.compile(rf"{re.escape(keyword)}[^\n]{{0,15}}", re.IGNORECASE)
        near = pattern.search(text)
        if near:
            date_match = _DATE_PATTERN.search(near.group(0))
            if date_match:
                parsed = _parse_date_str(date_match.group(1))
                if parsed:
                    return parsed

    fallback = _DATE_PATTERN.search(text)
    if fallback:
        return _parse_date_str(fallback.group(1))
    return None


def _parse_date_str(raw: str) -> date | None:
    try:
        return date_parser.parse(raw, dayfirst=True).date()
    except (ValueError, OverflowError):
        return None


def _extract_invoice_number(text: str) -> str | None:
    for keyword in _INVOICE_NUMBER_KEYWORDS:
        pattern = re.compile(rf"{re.escape(keyword)}\s*[:.]?\s*([A-Za-z0-9\-/]+)", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def _extract_sender(text: str) -> str | None:
    """Nimmt die erste nichtleere, plausible Zeile als Absender an (Briefkopf-Position).

    Am unsichersten von allen Feldern - im UI als geringe Konfidenz kennzeichnen.
    """
    for line in text.splitlines():
        candidate = line.strip()
        if len(candidate) >= 3 and not candidate[0].isdigit():
            return candidate
    return None


def find_iban(text: str) -> str | None:
    """Findet die erste plausible IBAN im Text (fuer die Girocode-Prüfmaske, immer manuell zu prüfen)."""
    match = _IBAN_PATTERN.search(text.replace("\n", " "))
    if match:
        return match.group(1).replace(" ", "")
    return None


def find_bic(text: str) -> str | None:
    for keyword in _BIC_KEYWORDS:
        pattern = re.compile(rf"{re.escape(keyword)}[:\s]{{0,5}}([A-Z0-9]{{8,11}})", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            return match.group(1).upper()
    return None


def extract_fields(text: str) -> ExtractedFields:
    if not text or not text.strip():
        return ExtractedFields()

    gross, net, vat_amount, vat_rate = _extract_amounts(text)

    return ExtractedFields(
        sender_name=_extract_sender(text),
        invoice_number=_extract_invoice_number(text),
        invoice_date=_extract_date(text),
        amount_gross=gross,
        amount_net=net,
        vat_amount=vat_amount,
        vat_rate=vat_rate,
        sender_low_confidence=True,
    )
