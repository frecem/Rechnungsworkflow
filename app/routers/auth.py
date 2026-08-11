from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import login_guard, password_reset
from app.services.auth import hash_password, verify_password
from app.services.settings_service import get_settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/setup")
def setup_form(request: Request, db: Session = Depends(get_db)):
    settings = get_settings(db)
    if settings.password_set:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "setup.html", {})


@router.post("/setup")
def setup_submit(
    request: Request,
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    settings = get_settings(db)
    if settings.password_set:
        return RedirectResponse("/login", status_code=303)

    if len(password) < 8 or password != password_confirm:
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"error": "Passwort muss mind. 8 Zeichen lang sein und mit der Bestätigung übereinstimmen."},
            status_code=400,
        )

    settings.admin_password_hash = hash_password(password)
    db.commit()

    request.session["authenticated"] = True
    return RedirectResponse("/", status_code=303)


@router.get("/login")
def login_form(request: Request, reset: str = "", db: Session = Depends(get_db)):
    settings = get_settings(db)
    if not settings.password_set:
        return RedirectResponse("/setup", status_code=303)
    if request.session.get("authenticated"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"password_reset_done": bool(reset)})


@router.post("/login")
def login_submit(request: Request, password: str = Form(...), db: Session = Depends(get_db)):
    if login_guard.is_locked():
        return templates.TemplateResponse(
            request,
            "login.html",
            {"locked": True, "unlock_minutes": (login_guard.seconds_until_unlock() // 60) + 1},
            status_code=429,
        )

    settings = get_settings(db)
    if not settings.password_set or not verify_password(password, settings.admin_password_hash):
        login_guard.register_failure()
        return templates.TemplateResponse(
            request, "login.html", {"error": "Falsches Passwort."}, status_code=400
        )

    login_guard.register_success()
    request.session["authenticated"] = True
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/forgot-password")
def forgot_password_form(request: Request, db: Session = Depends(get_db)):
    settings = get_settings(db)
    if not settings.password_set:
        return RedirectResponse("/setup", status_code=303)
    return templates.TemplateResponse(request, "forgot_password.html", {})


@router.post("/forgot-password")
def forgot_password_submit(request: Request, db: Session = Depends(get_db)):
    ok, message = password_reset.request_reset(db, str(request.base_url))
    return templates.TemplateResponse(request, "forgot_password.html", {"result": message, "ok": ok})


@router.get("/reset-password")
def reset_password_form(request: Request, token: str = "", db: Session = Depends(get_db)):
    if not password_reset.validate_token(db, token):
        return templates.TemplateResponse(request, "reset_password.html", {"invalid": True})
    return templates.TemplateResponse(request, "reset_password.html", {"token": token})


@router.post("/reset-password")
def reset_password_submit(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    if not password_reset.validate_token(db, token):
        return templates.TemplateResponse(request, "reset_password.html", {"invalid": True}, status_code=400)

    if len(new_password) < 8 or new_password != new_password_confirm:
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {
                "token": token,
                "error": "Passwort muss mind. 8 Zeichen lang sein und mit der Bestätigung übereinstimmen.",
            },
            status_code=400,
        )

    password_reset.complete_reset(db, token, new_password)
    login_guard.register_success()
    return RedirectResponse("/login?reset=1", status_code=303)
