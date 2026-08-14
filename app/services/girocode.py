"""EPC-QR-Code (Girocode) fuer SEPA-Ueberweisungen, siehe EPC069-12 / de.wikipedia.org/wiki/EPC-QR-Code.

Der Code kodiert die Zahlungsdaten des Rechnungsstellers (Empfaenger der Zahlung), damit
die Nutzerin ihn mit einer Banking-App scannen und die Rechnung damit bezahlen kann.
"""

import io
import re
from decimal import Decimal, InvalidOperation

import qrcode

_WHITESPACE_RE = re.compile(r"\s+")
_IBAN_FORMAT_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")
_MAX_PAYLOAD_BYTES = 331


class InvalidPaymentData(Exception):
    pass


def normalize_iban(raw: str) -> str:
    return _WHITESPACE_RE.sub("", raw).upper()


def validate_iban(iban: str) -> bool:
    iban = normalize_iban(iban)
    if not _IBAN_FORMAT_RE.match(iban):
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(numeric) % 97 == 1


def build_epc_payload(recipient_name: str, iban: str, bic: str | None, amount: Decimal, reference: str) -> str:
    recipient_name = recipient_name.strip()
    reference = reference.strip()
    iban = normalize_iban(iban)

    if not recipient_name:
        raise InvalidPaymentData("Empfänger darf nicht leer sein")
    if not validate_iban(iban):
        raise InvalidPaymentData("IBAN ist ungültig (Prüfsumme stimmt nicht)")
    if amount <= 0:
        raise InvalidPaymentData("Betrag muss größer als 0 sein")

    lines = [
        "BCD",
        "002",
        "1",
        "SCT",
        (bic or "").strip().upper(),
        recipient_name[:70],
        iban,
        f"EUR{amount:.2f}",
        "",
        "",
        reference[:140],
    ]
    payload = "\n".join(lines)
    if len(payload.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise InvalidPaymentData("Zahlungsdaten sind zu lang für einen EPC-QR-Code")
    return payload


_AMOUNT_LINE_RE = re.compile(r"^[A-Z]{3}(\d+(?:[.,]\d{1,2})?)$")


def parse_epc_payload(payload: str) -> dict | None:
    """Zerlegt einen bereits auf dem Beleg vorhandenen EPC-QR-Code in seine

    Zahlungsfelder - das Gegenstueck zu build_epc_payload(). Viele deutsche
    Rechnungen (v.a. von Versorgern) drucken den Girocode schon auf die
    Rechnung; wird er beim Import erkannt (siehe app/services/qr_scan.py),
    lassen sich die Zahlungsdaten direkt daraus vorbefuellen statt sie per
    Texterkennung zu erraten. Gibt None zurueck, wenn payload keinen
    plausiblen EPC069-12-Code enthaelt (z.B. ein anderer QR-Code auf dem
    Beleg, etwa eine Tracking- oder Portal-URL) oder die IBAN ungueltig ist.
    """
    lines = payload.replace("\r\n", "\n").split("\n")
    if len(lines) < 7 or lines[0].strip() != "BCD":
        return None

    bic = lines[4].strip() if len(lines) > 4 else ""
    recipient_name = lines[5].strip() if len(lines) > 5 else ""
    iban = normalize_iban(lines[6]) if len(lines) > 6 else ""
    amount_raw = lines[7].strip() if len(lines) > 7 else ""
    structured_ref = lines[9].strip() if len(lines) > 9 else ""
    unstructured_ref = lines[10].strip() if len(lines) > 10 else ""

    if not validate_iban(iban):
        return None

    amount = None
    amount_match = _AMOUNT_LINE_RE.match(amount_raw)
    if amount_match:
        try:
            amount = Decimal(amount_match.group(1).replace(",", "."))
        except InvalidOperation:
            amount = None

    return {
        "recipient_name": recipient_name or None,
        "iban": iban,
        "bic": bic or None,
        "amount": amount,
        "reference": structured_ref or unstructured_ref or None,
    }


def generate_qr_png(payload: str) -> bytes:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
