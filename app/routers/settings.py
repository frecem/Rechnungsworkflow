from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FORWARD_TARGETS
from app.services.auth import hash_password, verify_password
from app.services.reminders import run_reminder_check
from app.services.settings_service import get_settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/settings")
def settings_form(request: Request, db: Session = Depends(get_db)):
    settings = get_settings(db)
    return templates.TemplateResponse(
        request, "settings.html", {"settings": settings, "forward_targets": FORWARD_TARGETS}
    )


@router.post("/settings")
def settings_save(
    request: Request,
    imap_host: str = Form(""),
    imap_port: int = Form(993),
    imap_user: str = Form(""),
    imap_app_password: str = Form(""),
    imap_mailbox: str = Form("INBOX"),
    smtp_host: str = Form(""),
    smtp_port: int = Form(587),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    steuer_email: str = Form(""),
    paperless_email: str = Form(""),
    girocode_email: str = Form(""),
    default_forward_target: str = Form("steuer"),
    reminder_email: str = Form(""),
    reminder_days_before: int = Form(3),
    categories: str = Form(""),
    db: Session = Depends(get_db),
):
    settings = get_settings(db)

    settings.imap_host = imap_host or None
    settings.imap_port = imap_port
    settings.imap_user = imap_user or None
    if imap_app_password:
        settings.imap_app_password = imap_app_password
    settings.imap_mailbox = imap_mailbox or "INBOX"

    settings.smtp_host = smtp_host or None
    settings.smtp_port = smtp_port
    settings.smtp_user = smtp_user or None
    if smtp_password:
        settings.smtp_password = smtp_password

    settings.steuer_email = steuer_email or None
    settings.paperless_email = paperless_email or None
    settings.girocode_email = girocode_email or None
    settings.default_forward_target = (
        default_forward_target if default_forward_target in FORWARD_TARGETS else "steuer"
    )
    settings.reminder_email = reminder_email or None
    settings.reminder_days_before = reminder_days_before
    settings.categories = categories or settings.categories

    db.commit()

    return templates.TemplateResponse(
        request,
        "settings.html",
        {"settings": settings, "forward_targets": FORWARD_TARGETS, "saved": True},
    )


@router.post("/settings/check-reminders")
def check_reminders_now(request: Request, db: Session = Depends(get_db)):
    settings = get_settings(db)
    count = run_reminder_check(db)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"settings": settings, "forward_targets": FORWARD_TARGETS, "reminder_check_result": count},
    )


@router.post("/settings/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    settings = get_settings(db)

    error = None
    if not verify_password(current_password, settings.admin_password_hash):
        error = "Aktuelles Passwort ist falsch."
    elif len(new_password) < 8 or new_password != new_password_confirm:
        error = "Neues Passwort muss mind. 8 Zeichen lang sein und mit der Bestätigung übereinstimmen."

    if error:
        return templates.TemplateResponse(
            request,
            "settings.html",
            {"settings": settings, "forward_targets": FORWARD_TARGETS, "password_error": error},
            status_code=400,
        )

    settings.admin_password_hash = hash_password(new_password)
    db.commit()

    return templates.TemplateResponse(
        request,
        "settings.html",
        {"settings": settings, "forward_targets": FORWARD_TARGETS, "password_saved": True},
    )
