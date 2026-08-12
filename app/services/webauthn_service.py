"""Passkey-Login (WebAuthn/FIDO2) als zusaetzlicher Anmeldeweg neben dem Passwort.

Einzelnutzer-Account, daher keine Benutzer-Suche noetig: Registrierung laeuft
ausschliesslich aus den (bereits eingeloggten) Einstellungen heraus, Login bietet
allen registrierten Credentials als allow_credentials an (kein Benutzername noetig,
das Betriebssystem/der Browser waehlt den passenden Passkey aus).

RP-ID/Origin werden dynamisch aus der Request-URL abgeleitet statt fest
konfiguriert, damit die App ohne zusaetzliche Einstellung hinter einem beliebigen
Domainnamen funktioniert - ein Passkey ist dadurch an genau den Hostnamen
gebunden, unter dem er registriert wurde (WebAuthn-Standardverhalten).
"""

from datetime import datetime

import webauthn
from fastapi import Request
from sqlalchemy.orm import Session
from webauthn.helpers.exceptions import InvalidAuthenticationResponse, InvalidRegistrationResponse
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

from app.models import WebauthnCredential
from app.services.settings_service import get_settings

RP_NAME = "Rechnungsworkflow"
CHALLENGE_SESSION_KEY = "webauthn_challenge"


def rp_id_from_request(request: Request) -> str:
    return request.url.hostname


def origin_from_request(request: Request) -> str:
    url = request.url
    return f"{url.scheme}://{url.hostname}" + (f":{url.port}" if url.port else "")


def begin_registration(db: Session, request: Request) -> dict:
    settings = get_settings(db)
    existing = db.query(WebauthnCredential).all()

    options = webauthn.generate_registration_options(
        rp_id=rp_id_from_request(request),
        rp_name=RP_NAME,
        user_name=settings.admin_username or "admin",
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=webauthn.base64url_to_bytes(c.credential_id)) for c in existing
        ],
    )
    request.session[CHALLENGE_SESSION_KEY] = webauthn.helpers.bytes_to_base64url(options.challenge)
    return webauthn.helpers.options_to_json(options)


def complete_registration(db: Session, request: Request, credential_json: str, label: str | None) -> WebauthnCredential:
    challenge = request.session.pop(CHALLENGE_SESSION_KEY, None)
    if not challenge:
        raise InvalidRegistrationResponse("Keine offene Registrierungs-Anfrage (Challenge fehlt/abgelaufen).")

    verification = webauthn.verify_registration_response(
        credential=credential_json,
        expected_challenge=webauthn.base64url_to_bytes(challenge),
        expected_rp_id=rp_id_from_request(request),
        expected_origin=origin_from_request(request),
    )

    record = WebauthnCredential(
        credential_id=webauthn.helpers.bytes_to_base64url(verification.credential_id),
        public_key=webauthn.helpers.bytes_to_base64url(verification.credential_public_key),
        sign_count=verification.sign_count,
        label=(label or "").strip() or None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def begin_authentication(db: Session, request: Request) -> dict:
    credentials = db.query(WebauthnCredential).all()
    options = webauthn.generate_authentication_options(
        rp_id=rp_id_from_request(request),
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=webauthn.base64url_to_bytes(c.credential_id)) for c in credentials
        ],
    )
    request.session[CHALLENGE_SESSION_KEY] = webauthn.helpers.bytes_to_base64url(options.challenge)
    return webauthn.helpers.options_to_json(options)


def complete_authentication(db: Session, request: Request, credential_json: str) -> bool:
    challenge = request.session.pop(CHALLENGE_SESSION_KEY, None)
    if not challenge:
        return False

    raw_id = webauthn.helpers.parse_authentication_credential_json(credential_json).raw_id
    stored = db.query(WebauthnCredential).filter_by(credential_id=webauthn.helpers.bytes_to_base64url(raw_id)).first()
    if stored is None:
        return False

    try:
        verification = webauthn.verify_authentication_response(
            credential=credential_json,
            expected_challenge=webauthn.base64url_to_bytes(challenge),
            expected_rp_id=rp_id_from_request(request),
            expected_origin=origin_from_request(request),
            credential_public_key=webauthn.base64url_to_bytes(stored.public_key),
            credential_current_sign_count=stored.sign_count,
        )
    except InvalidAuthenticationResponse:
        return False

    stored.sign_count = verification.new_sign_count
    stored.last_used_at = datetime.utcnow()
    db.commit()
    return True


def delete_credential(db: Session, credential_pk: int) -> None:
    db.query(WebauthnCredential).filter_by(id=credential_pk).delete()
    db.commit()
