import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings as bootstrap_settings
from app.database import SessionLocal
from app.routers import auth, board, email_sync, export, invoices, settings, stats, upload, webauthn
from app.services.auth import SESSION_REMEMBER_DAYS, session_is_valid
from app.services.imap_client import sync_new_invoices_standalone
from app.services.reminders import run_reminder_check_standalone, run_unprocessed_check_standalone
from app.services.settings_service import get_settings

PUBLIC_PATHS = {
    "/login",
    "/setup",
    "/forgot-password",
    "/reset-password",
    "/webauthn/login/options",
    "/webauthn/login/verify",
}
DEFAULT_SESSION_SECRET_KEY = "change-me-please-a-long-random-string"

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if bootstrap_settings.session_secret_key == DEFAULT_SESSION_SECRET_KEY:
        logger.warning(
            "SESSION_SECRET_KEY ist noch der Platzhalter-Wert aus .env.example! "
            "Bitte in .env auf einen zufälligen, geheimen String setzen "
            "(z.B. python3 -c \"import secrets; print(secrets.token_hex(32))\"), "
            "sonst ist die Login-Session leicht kompromittierbar."
        )

    scheduler.add_job(
        run_reminder_check_standalone,
        trigger="cron",
        hour=7,
        minute=0,
        id="due_date_reminder",
        replace_existing=True,
    )
    scheduler.add_job(
        sync_new_invoices_standalone,
        trigger="cron",
        minute=0,
        id="imap_auto_sync",
        replace_existing=True,
    )
    # Unbearbeitete-Rechnungen-Digest: werktags frueher, am Wochenende etwas spaeter -
    # zwei separate Cron-Jobs statt einem, da eine einzelne Cron-Angabe keine
    # unterschiedliche Uhrzeit je nach Wochentag ausdruecken kann.
    scheduler.add_job(
        run_unprocessed_check_standalone,
        trigger="cron",
        day_of_week="mon-fri",
        hour=8,
        minute=0,
        id="unprocessed_invoices_weekday",
        replace_existing=True,
    )
    scheduler.add_job(
        run_unprocessed_check_standalone,
        trigger="cron",
        day_of_week="sat,sun",
        hour=9,
        minute=0,
        id="unprocessed_invoices_weekend",
        replace_existing=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Rechnungsworkflow", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(board.router)
app.include_router(invoices.router)
app.include_router(upload.router)
app.include_router(email_sync.router)
app.include_router(export.router)
app.include_router(stats.router)
app.include_router(webauthn.router)


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static/"):
        return await call_next(request)

    db = SessionLocal()
    try:
        app_settings = get_settings(db)
    finally:
        db.close()

    if not app_settings.password_set:
        if path != "/setup":
            return RedirectResponse("/setup", status_code=303)
        return await call_next(request)

    if path in PUBLIC_PATHS:
        return await call_next(request)

    if not session_is_valid(request):
        return RedirectResponse("/login", status_code=303)

    return await call_next(request)


# Starlette inserts each add_middleware() call at the front of the stack, so the
# middleware added last runs first per request. SessionMiddleware must run before
# require_login (which reads request.session), so it is added after that middleware
# is registered.
#
# https_only is intentionally left at its default (False): a reverse proxy in front
# of this app terminates TLS, and the app itself must stay reachable via plain HTTP
# and HTTPS through that proxy - a secure-only cookie would break the HTTP path.
#
# max_age is the outer cookie lifetime ceiling ("Angemeldet bleiben" duration); the
# actual per-login expiry (short vs. remembered) is enforced separately in
# app.services.auth.session_is_valid via a timestamp stored inside the session itself.
app.add_middleware(
    SessionMiddleware,
    secret_key=bootstrap_settings.session_secret_key,
    same_site="lax",
    max_age=SESSION_REMEMBER_DAYS * 24 * 60 * 60,
)


@app.get("/")
def root():
    return RedirectResponse("/board")
