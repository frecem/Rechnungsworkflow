"""Sucht in einem hochgeladenen Beleg nach einem bereits vorhandenen EPC-QR-Code

(Girocode) - viele deutsche Rechnungen (v.a. Versorger) drucken den Code schon
auf die Rechnung, damit man sie direkt per Banking-App bezahlen kann. Wird einer
gefunden, koennen die Zahlungsdaten fuer die eigene Girocode-Maske (siehe
app/routers/invoices.py, girocode_form) direkt daraus vorbefuellt werden, statt
sie per Texterkennung zu erraten.

Erfordert das Systempaket libzbar0 (siehe Dockerfile). Fehlt es, wird kein Fehler
geworfen, sondern None zurueckgegeben - identisch zum OCR-Fallback-Verhalten in
ocr.py. Alle extrahierten Felder bleiben ohnehin manuell editierbar.
"""

import logging

from app.services import girocode

logger = logging.getLogger(__name__)


def find_epc_payment_data(content: bytes, mime_type: str | None) -> dict | None:
    """Gibt die Zahlungsdaten des ersten gefundenen EPC-Girocodes zurueck (oder None)."""
    for image in _extract_images(content, mime_type):
        payload = _find_epc_qr_in_image(image)
        if payload is not None:
            parsed = girocode.parse_epc_payload(payload)
            if parsed is not None:
                return parsed
    return None


def _extract_images(content: bytes, mime_type: str | None) -> list:
    if mime_type == "application/pdf":
        try:
            import pdf2image

            return pdf2image.convert_from_bytes(content)
        except Exception:
            logger.warning(
                "PDF-zu-Bild-Konvertierung fuer QR-Suche fehlgeschlagen (poppler-utils installiert?)",
                exc_info=True,
            )
            return []
    if mime_type and mime_type.startswith("image/"):
        try:
            import io

            from PIL import Image

            return [Image.open(io.BytesIO(content))]
        except Exception:
            logger.warning("Bild konnte fuer QR-Suche nicht geoeffnet werden", exc_info=True)
            return []
    return []


def _find_epc_qr_in_image(image) -> str | None:
    try:
        from pyzbar.pyzbar import decode
    except Exception:
        logger.warning("pyzbar/libzbar nicht verfuegbar - QR-Erkennung uebersprungen", exc_info=True)
        return None

    try:
        results = decode(image)
    except Exception:
        logger.warning("QR-Code-Erkennung fehlgeschlagen", exc_info=True)
        return None

    for result in results:
        try:
            data = result.data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if data.startswith("BCD"):
            return data
    return None
