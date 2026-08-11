from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
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
def login_form(request: Request, db: Session = Depends(get_db)):
    settings = get_settings(db)
    if not settings.password_set:
        return RedirectResponse("/setup", status_code=303)
    if request.session.get("authenticated"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
def login_submit(request: Request, password: str = Form(...), db: Session = Depends(get_db)):
    settings = get_settings(db)
    if not settings.password_set or not verify_password(password, settings.admin_password_hash):
        return templates.TemplateResponse(
            request, "login.html", {"error": "Falsches Passwort."}, status_code=400
        )

    request.session["authenticated"] = True
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
