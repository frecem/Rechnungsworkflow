from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings as bootstrap_settings
from app.database import SessionLocal
from app.routers import auth, board, email_sync, export, invoices, settings, upload
from app.services.settings_service import get_settings

PUBLIC_PATHS = {"/login", "/setup"}

app = FastAPI(title="Rechnungsworkflow")

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(board.router)
app.include_router(invoices.router)
app.include_router(upload.router)
app.include_router(email_sync.router)
app.include_router(export.router)


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

    if not request.session.get("authenticated"):
        return RedirectResponse("/login", status_code=303)

    return await call_next(request)


# Starlette inserts each add_middleware() call at the front of the stack, so the
# middleware added last runs first per request. SessionMiddleware must run before
# require_login (which reads request.session), so it is added after that middleware
# is registered.
app.add_middleware(SessionMiddleware, secret_key=bootstrap_settings.session_secret_key, same_site="lax")


@app.get("/")
def root():
    return RedirectResponse("/board")
