import smtplib
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FORWARD_TARGETS, STATUSES, Invoice
from app.services import extraction, girocode, storage
from app.services.settings_service import get_settings
from app.services.smtp_client import SmtpNotConfigured, send_girocode, send_invoice_copy
from app.services.status import InvalidStatusTransition, change_status

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _parse_decimal(raw: str | None) -> Decimal | None:
    if not raw or not raw.strip():
        return None
    try:
        return Decimal(raw.strip().replace(",", "."))
    except InvalidOperation:
        return None


def _parse_date(raw: str | None) -> date | None:
    if not raw or not raw.strip():
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _get_invoice_or_404(db: Session, invoice_id: int) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Rechnung nicht gefunden")
    return invoice


@router.get("/invoices")
def list_invoices(request: Request, status: str | None = None, q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Invoice)
    if status:
        query = query.filter(Invoice.status == status)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Invoice.sender_name.ilike(like)) | (Invoice.invoice_number.ilike(like))
        )
    invoices = query.order_by(Invoice.created_at.desc()).all()

    return templates.TemplateResponse(
        request,
        "invoice_list.html",
        {
            "invoices": invoices,
            "statuses": STATUSES,
            "current_status": status or "",
            "q": q or "",
        },
    )


@router.get("/invoices/{invoice_id}")
def invoice_detail(request: Request, invoice_id: int, db: Session = Depends(get_db)):
    invoice = _get_invoice_or_404(db, invoice_id)
    settings = get_settings(db)
    return templates.TemplateResponse(
        request,
        "invoice_detail.html",
        {
            "invoice": invoice,
            "categories": settings.category_list,
        },
    )


@router.get("/invoices/{invoice_id}/file")
def invoice_file(invoice_id: int, db: Session = Depends(get_db)):
    invoice = _get_invoice_or_404(db, invoice_id)
    content = storage.read_file(invoice.file_path)
    media_type = invoice.file_mime_type or "application/octet-stream"
    return Response(content=content, media_type=media_type)


@router.post("/invoices/{invoice_id}/save")
def save_invoice(
    invoice_id: int,
    sender_name: str = Form(""),
    invoice_number: str = Form(""),
    invoice_date: str = Form(""),
    due_date: str = Form(""),
    amount_gross: str = Form(""),
    amount_net: str = Form(""),
    vat_amount: str = Form(""),
    vat_rate: str = Form(""),
    currency: str = Form("EUR"),
    category: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    invoice = _get_invoice_or_404(db, invoice_id)

    invoice.sender_name = sender_name or None
    invoice.invoice_number = invoice_number or None
    invoice.invoice_date = _parse_date(invoice_date)
    invoice.due_date = _parse_date(due_date)
    invoice.amount_gross = _parse_decimal(amount_gross)
    invoice.amount_net = _parse_decimal(amount_net)
    invoice.vat_amount = _parse_decimal(vat_amount)
    invoice.vat_rate = _parse_decimal(vat_rate)
    invoice.currency = currency or "EUR"
    invoice.category = category or None
    invoice.notes = notes or None
    db.commit()

    if invoice.status in ("extracted", "rejected"):
        change_status(db, invoice, "reviewed", note="Felder geprueft/bearbeitet")

    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/approve")
def approve_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = _get_invoice_or_404(db, invoice_id)
    try:
        change_status(db, invoice, "approved")
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/reject")
def reject_invoice(invoice_id: int, note: str = Form(""), db: Session = Depends(get_db)):
    invoice = _get_invoice_or_404(db, invoice_id)
    try:
        change_status(db, invoice, "rejected", note=note or None)
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.get("/invoices/{invoice_id}/girocode")
def girocode_form(request: Request, invoice_id: int, db: Session = Depends(get_db)):
    invoice = _get_invoice_or_404(db, invoice_id)
    if invoice.status != "approved":
        raise HTTPException(status_code=400, detail="Rechnung muss zuerst freigegeben werden")

    settings = get_settings(db)
    raw_text = invoice.raw_extracted_text or ""

    prefill = {
        "recipient_name": invoice.payment_recipient_name or invoice.sender_name or "",
        "iban": invoice.payment_iban or extraction.find_iban(raw_text) or "",
        "bic": invoice.payment_bic or extraction.find_bic(raw_text) or "",
        "amount": invoice.amount_gross or "",
        "reference": invoice.payment_reference
        or (f"Rechnung {invoice.invoice_number}" if invoice.invoice_number else ""),
    }

    return templates.TemplateResponse(
        request,
        "girocode.html",
        {
            "invoice": invoice,
            "prefill": prefill,
            "forward_targets": FORWARD_TARGETS,
            "default_forward_target": settings.default_forward_target,
            "girocode_email": settings.girocode_email,
            "steuer_email": settings.steuer_email,
            "paperless_email": settings.paperless_email,
        },
    )


@router.post("/invoices/{invoice_id}/girocode")
def girocode_submit(
    request: Request,
    invoice_id: int,
    recipient_name: str = Form(...),
    iban: str = Form(...),
    bic: str = Form(""),
    amount: str = Form(...),
    reference: str = Form(""),
    forward_target: str = Form(...),
    db: Session = Depends(get_db),
):
    invoice = _get_invoice_or_404(db, invoice_id)
    if invoice.status != "approved":
        raise HTTPException(status_code=400, detail="Rechnung muss zuerst freigegeben werden")

    settings = get_settings(db)

    def render_error(message: str):
        return templates.TemplateResponse(
            request,
            "girocode.html",
            {
                "invoice": invoice,
                "prefill": {
                    "recipient_name": recipient_name,
                    "iban": iban,
                    "bic": bic,
                    "amount": amount,
                    "reference": reference,
                },
                "forward_targets": FORWARD_TARGETS,
                "default_forward_target": forward_target,
                "girocode_email": settings.girocode_email,
                "steuer_email": settings.steuer_email,
                "paperless_email": settings.paperless_email,
                "error": message,
            },
            status_code=400,
        )

    parsed_amount = _parse_decimal(amount)
    if parsed_amount is None:
        return render_error("Betrag ist ungültig.")
    if forward_target not in FORWARD_TARGETS:
        return render_error("Ungültiges Weiterleitungsziel.")
    if not settings.girocode_email:
        return render_error("Keine Girocode-Empfänger-Adresse in den Einstellungen hinterlegt.")

    target_emails: list[str] = []
    if forward_target in ("steuer", "both"):
        if not settings.steuer_email:
            return render_error("Keine Steuer-E-Mail-Adresse in den Einstellungen hinterlegt.")
        target_emails.append(settings.steuer_email)
    if forward_target in ("paperless", "both"):
        if not settings.paperless_email:
            return render_error("Keine Paperless-ngx-E-Mail-Adresse in den Einstellungen hinterlegt.")
        target_emails.append(settings.paperless_email)

    try:
        payload = girocode.build_epc_payload(recipient_name, iban, bic or None, parsed_amount, reference)
    except girocode.InvalidPaymentData as exc:
        return render_error(str(exc))

    invoice.payment_recipient_name = recipient_name
    invoice.payment_iban = girocode.normalize_iban(iban)
    invoice.payment_bic = (bic or None) and bic.strip().upper()
    invoice.payment_reference = reference
    db.commit()

    png_bytes = girocode.generate_qr_png(payload)

    try:
        send_girocode(db, invoice, settings.girocode_email, png_bytes)
    except SmtpNotConfigured as exc:
        return render_error(str(exc))
    except (smtplib.SMTPException, OSError) as exc:
        return render_error(f"Girocode-Versand fehlgeschlagen: {exc}")

    invoice.girocode_sent_at = datetime.utcnow()
    db.commit()

    try:
        for target_email in target_emails:
            send_invoice_copy(db, invoice, target_email)
    except (smtplib.SMTPException, OSError) as exc:
        return render_error(
            f"Girocode wurde versendet, aber die Weiterleitung der Rechnung ist fehlgeschlagen: {exc}"
        )

    invoice.forwarded_to = ", ".join(target_emails)
    invoice.forwarded_at = datetime.utcnow()
    db.commit()

    try:
        change_status(db, invoice, "forwarded")
    except InvalidStatusTransition as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)
