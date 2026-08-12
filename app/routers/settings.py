from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FORWARD_TARGETS, AppSettings, WebauthnCredential
from app.services import imap_client, smtp_client
from app.services.auth import hash_password, verify_password
from app.services.backup import backup_filename, build_backup_zip, is_backup_overdue
from app.services.reminders import run_reminder_check
from app.services.settings_service import add_category, delete_category, get_settings, rename_category

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _settings_response(
    request: Request, db: Session, settings: AppSettings, extra: dict | None = None, status_code: int = 200
):
    context = {
        "settings": settings,
        "forward_targets": FORWARD_TARGETS,
        "backup_overdue": is_backup_overdue(settings),
        "passkeys": db.query(WebauthnCredential).order_by(WebauthnCredential.created_at).all(),
    }
    context.update(extra or {})
    return templates.TemplateResponse(request, "settings.html", context, status_code=status_code)


@router.get("/settings")
def settings_form(request: Request, db: Session = Depends(get_db)):
    settings = get_settings(db)
    return _settings_response(request, db, settings)


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

    db.commit()

    return _settings_response(request, db, settings, {"saved": True})


@router.post("/settings/test-imap")
def test_imap(
    request: Request,
    imap_host: str = Form(""),
    imap_port: int = Form(993),
    imap_user: str = Form(""),
    imap_app_password: str = Form(""),
    imap_mailbox: str = Form("INBOX"),
    db: Session = Depends(get_db),
):
    settings = get_settings(db)
    password = imap_app_password or settings.imap_app_password

    if not imap_host or not imap_user or not password:
        imap_test_result = (False, "Host, Benutzer und Passwort müssen ausgefüllt sein.")
    else:
        imap_test_result = imap_client.test_connection(
            imap_host, imap_port, imap_user, password, imap_mailbox or "INBOX"
        )

    # Eingegebene, noch nicht gespeicherte Werte im Formular anzeigen (nicht committen)
    settings.imap_host = imap_host or None
    settings.imap_port = imap_port
    settings.imap_user = imap_user or None
    settings.imap_mailbox = imap_mailbox or "INBOX"

    return _settings_response(request, db, settings, {"imap_test_result": imap_test_result})


@router.post("/settings/test-smtp")
def test_smtp(
    request: Request,
    smtp_host: str = Form(""),
    smtp_port: int = Form(587),
    smtp_user: str = Form(""),
    smtp_password: str = Form(""),
    db: Session = Depends(get_db),
):
    settings = get_settings(db)
    password = smtp_password or settings.smtp_password

    if not smtp_host or not smtp_user or not password:
        smtp_test_result = (False, "Host, Benutzer und Passwort müssen ausgefüllt sein.")
    else:
        smtp_test_result = smtp_client.test_connection(smtp_host, smtp_port, smtp_user, password)

    settings.smtp_host = smtp_host or None
    settings.smtp_port = smtp_port
    settings.smtp_user = smtp_user or None

    return _settings_response(request, db, settings, {"smtp_test_result": smtp_test_result})


@router.post("/settings/categories")
def add_category_route(name: str = Form(...), db: Session = Depends(get_db)):
    add_category(db, name)
    return RedirectResponse("/settings", status_code=303)


@router.post("/settings/categories/rename")
def rename_category_route(old_name: str = Form(...), new_name: str = Form(...), db: Session = Depends(get_db)):
    rename_category(db, old_name, new_name)
    return RedirectResponse("/settings", status_code=303)


@router.post("/settings/categories/delete")
def delete_category_route(name: str = Form(...), db: Session = Depends(get_db)):
    delete_category(db, name)
    return RedirectResponse("/settings", status_code=303)


@router.post("/settings/check-reminders")
def check_reminders_now(request: Request, db: Session = Depends(get_db)):
    settings = get_settings(db)
    count = run_reminder_check(db)
    return _settings_response(request, db, settings, {"reminder_check_result": count})


@router.get("/settings/backup")
def download_backup(db: Session = Depends(get_db)):
    content = build_backup_zip()

    settings = get_settings(db)
    settings.last_backup_at = datetime.utcnow()
    db.commit()

    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={backup_filename()}"},
    )


@router.post("/settings/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_username: str = Form(""),
    new_password: str = Form(""),
    new_password_confirm: str = Form(""),
    db: Session = Depends(get_db),
):
    settings = get_settings(db)

    error = None
    if not verify_password(current_password, settings.admin_password_hash):
        error = "Aktuelles Passwort ist falsch."
    elif new_password and (len(new_password) < 8 or new_password != new_password_confirm):
        error = "Neues Passwort muss mind. 8 Zeichen lang sein und mit der Bestätigung übereinstimmen."
    elif not new_password and not new_username.strip():
        error = "Bitte neuen Benutzernamen und/oder neues Passwort angeben."

    if error:
        return _settings_response(request, db, settings, {"password_error": error}, status_code=400)

    if new_username.strip():
        settings.admin_username = new_username.strip()
    if new_password:
        settings.admin_password_hash = hash_password(new_password)
    db.commit()

    return _settings_response(request, db, settings, {"password_saved": True})
