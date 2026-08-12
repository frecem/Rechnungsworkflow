import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse

from app.database import get_db
from app.models import WebauthnCredential
from app.services import login_guard
from app.services.auth import start_session
from app.services.webauthn_service import begin_authentication, begin_registration, complete_authentication, complete_registration, delete_credential

router = APIRouter(prefix="/webauthn")
logger = logging.getLogger(__name__)


def _options_response(options_json: str) -> Response:
    # begin_registration()/begin_authentication() already return a JSON *string*
    # (webauthn.helpers.options_to_json) - wrapping that in JSONResponse() would
    # double-encode it into a JSON string literal instead of an object, so the
    # raw string is sent through as-is with the right content type.
    return Response(content=options_json, media_type="application/json")


@router.post("/register/options")
def register_options(request: Request, db: Session = Depends(get_db)):
    return _options_response(begin_registration(db, request))


@router.post("/register/verify")
async def register_verify(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    try:
        complete_registration(db, request, body["credential"], body.get("label"))
    except InvalidRegistrationResponse as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    return JSONResponse({"ok": True})


@router.post("/login/options")
def login_options(request: Request, db: Session = Depends(get_db)):
    if db.query(WebauthnCredential).count() == 0:
        return JSONResponse({"error": "Keine Passkeys registriert."}, status_code=400)
    return _options_response(begin_authentication(db, request))


@router.post("/login/verify")
async def login_verify(request: Request, db: Session = Depends(get_db)):
    if login_guard.is_locked():
        return JSONResponse({"ok": False, "error": "Login vorübergehend gesperrt."}, status_code=429)

    body = await request.json()
    try:
        ok = complete_authentication(db, request, body["credential"])
    except InvalidAuthenticationResponse:
        ok = False

    if not ok:
        login_guard.register_failure()
        return JSONResponse({"ok": False, "error": "Passkey-Anmeldung fehlgeschlagen."}, status_code=400)

    login_guard.register_success()
    start_session(request, remember=True)
    return JSONResponse({"ok": True})


@router.post("/credentials/{credential_id}/delete")
def delete_credential_route(credential_id: int, db: Session = Depends(get_db)):
    delete_credential(db, credential_id)
    return JSONResponse({"ok": True})
