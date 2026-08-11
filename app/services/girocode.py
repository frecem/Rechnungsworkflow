"""EPC-QR-Code (Girocode) fuer SEPA-Ueberweisungen, siehe EPC069-12 / de.wikipedia.org/wiki/EPC-QR-Code.

Der Code kodiert die Zahlungsdaten des Rechnungsstellers (Empfaenger der Zahlung), damit
die Nutzerin ihn mit einer Banking-App scannen und die Rechnung damit bezahlen kann.
"""

import io
import re
from decimal import Decimal

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


def generate_qr_png(payload: str) -> bytes:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
