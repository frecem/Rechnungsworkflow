"""Textgewinnung aus hochgeladenen Belegen (PDF mit Textlayer, gescanntes PDF, Foto).

Erfordert fuer den OCR-Fallback die Systempakete `tesseract-ocr` (+ `tesseract-ocr-deu`)
und `poppler-utils` (fuer `pdftoppm`). Ist eines davon nicht installiert, wird eine
leere Zeichenkette zurueckgegeben statt eines Absturzes - der Nutzer traegt die Felder
dann einfach manuell ein.
"""

import logging

logger = logging.getLogger(__name__)

MIN_TEXT_LAYER_CHARS = 20  # ab dieser Laenge gilt ein PDF-Textlayer als "vorhanden"


def extract_text(content: bytes, mime_type: str | None) -> str:
    if mime_type == "application/pdf":
        text = _extract_pdf_text_layer(content)
        if len(text.strip()) >= MIN_TEXT_LAYER_CHARS:
            return text
        return _ocr_pdf(content)
    if mime_type and mime_type.startswith("image/"):
        return _ocr_image(content)
    return ""


def _extract_pdf_text_layer(content: bytes) -> str:
    try:
        import io

        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        logger.warning("PDF-Textlayer-Extraktion fehlgeschlagen", exc_info=True)
        return ""


def _ocr_pdf(content: bytes) -> str:
    try:
        import pdf2image

        images = pdf2image.convert_from_bytes(content)
    except Exception:
        logger.warning(
            "PDF-zu-Bild-Konvertierung fehlgeschlagen (poppler-utils installiert?)",
            exc_info=True,
        )
        return ""

    return "\n".join(_ocr_pil_image(img) for img in images)


def _ocr_image(content: bytes) -> str:
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(content))
        return _ocr_pil_image(img)
    except Exception:
        logger.warning("Bild-OCR fehlgeschlagen", exc_info=True)
        return ""


def _ocr_pil_image(img) -> str:
    try:
        import pytesseract

        return pytesseract.image_to_string(img, lang="deu+eng")
    except Exception:
        logger.warning("Tesseract-OCR fehlgeschlagen (tesseract-ocr installiert?)", exc_info=True)
        return ""
