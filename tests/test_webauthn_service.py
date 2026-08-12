from types import SimpleNamespace
from unittest.mock import patch

import pytest
import webauthn
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import URL
from webauthn.helpers.exceptions import InvalidRegistrationResponse

from app.database import Base
from app.models import WebauthnCredential
from app.services import webauthn_service

CHALLENGE = webauthn.helpers.bytes_to_base64url(b"some-challenge-bytes")


class FakeRequest:
    def __init__(self, url: str):
        self.url = URL(url)
        self.session = {}


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_rp_id_and_origin_from_request():
    request = FakeRequest("https://rechnungen.example.com/settings")
    assert webauthn_service.rp_id_from_request(request) == "rechnungen.example.com"
    assert webauthn_service.origin_from_request(request) == "https://rechnungen.example.com"


def test_rp_id_and_origin_include_nonstandard_port():
    request = FakeRequest("http://localhost:8123/login")
    assert webauthn_service.rp_id_from_request(request) == "localhost"
    assert webauthn_service.origin_from_request(request) == "http://localhost:8123"


def test_begin_registration_stores_challenge_in_session(db):
    request = FakeRequest("https://rechnungen.example.com/settings")
    options_json = webauthn_service.begin_registration(db, request)

    assert "challenge" in options_json
    assert webauthn_service.CHALLENGE_SESSION_KEY in request.session


def test_begin_registration_excludes_existing_credentials(db):
    db.add(WebauthnCredential(credential_id="AAAA", public_key="BBBB", sign_count=0))
    db.commit()

    request = FakeRequest("https://rechnungen.example.com/settings")
    options_json = webauthn_service.begin_registration(db, request)

    assert "AAAA" in options_json or "excludeCredentials" in options_json


def test_complete_registration_without_challenge_raises(db):
    request = FakeRequest("https://rechnungen.example.com/settings")
    with pytest.raises(InvalidRegistrationResponse):
        webauthn_service.complete_registration(db, request, "{}", "Laptop")


def test_complete_registration_stores_credential(db):
    request = FakeRequest("https://rechnungen.example.com/settings")
    request.session[webauthn_service.CHALLENGE_SESSION_KEY] = CHALLENGE

    fake_verification = SimpleNamespace(
        credential_id=b"credential-id-bytes",
        credential_public_key=b"public-key-bytes",
        sign_count=0,
    )

    with patch("app.services.webauthn_service.webauthn.verify_registration_response", return_value=fake_verification):
        record = webauthn_service.complete_registration(db, request, "{}", "Mein Laptop")

    assert record.label == "Mein Laptop"
    assert record.credential_id == webauthn.helpers.bytes_to_base64url(b"credential-id-bytes")
    assert webauthn_service.CHALLENGE_SESSION_KEY not in request.session
    assert db.query(WebauthnCredential).count() == 1


def test_begin_authentication_stores_challenge(db):
    request = FakeRequest("https://rechnungen.example.com/login")
    options_json = webauthn_service.begin_authentication(db, request)

    assert "challenge" in options_json
    assert webauthn_service.CHALLENGE_SESSION_KEY in request.session


def test_complete_authentication_without_challenge_returns_false(db):
    request = FakeRequest("https://rechnungen.example.com/login")
    assert webauthn_service.complete_authentication(db, request, "{}") is False


def test_complete_authentication_unknown_credential_returns_false(db):
    request = FakeRequest("https://rechnungen.example.com/login")
    request.session[webauthn_service.CHALLENGE_SESSION_KEY] = CHALLENGE

    fake_credential = SimpleNamespace(raw_id=b"unknown-id")
    with patch(
        "app.services.webauthn_service.webauthn.helpers.parse_authentication_credential_json",
        return_value=fake_credential,
    ):
        assert webauthn_service.complete_authentication(db, request, "{}") is False


def test_complete_authentication_success_updates_sign_count_and_last_used(db):
    stored = WebauthnCredential(
        credential_id=webauthn.helpers.bytes_to_base64url(b"credential-id-bytes"),
        public_key=webauthn.helpers.bytes_to_base64url(b"public-key-bytes"),
        sign_count=3,
    )
    db.add(stored)
    db.commit()

    request = FakeRequest("https://rechnungen.example.com/login")
    request.session[webauthn_service.CHALLENGE_SESSION_KEY] = CHALLENGE

    fake_credential = SimpleNamespace(raw_id=b"credential-id-bytes")
    fake_verification = SimpleNamespace(new_sign_count=4)

    with (
        patch(
            "app.services.webauthn_service.webauthn.helpers.parse_authentication_credential_json",
            return_value=fake_credential,
        ),
        patch("app.services.webauthn_service.webauthn.verify_authentication_response", return_value=fake_verification),
    ):
        result = webauthn_service.complete_authentication(db, request, "{}")

    assert result is True
    db.refresh(stored)
    assert stored.sign_count == 4
    assert stored.last_used_at is not None
    assert webauthn_service.CHALLENGE_SESSION_KEY not in request.session


def test_delete_credential_removes_row(db):
    record = WebauthnCredential(credential_id="AAAA", public_key="BBBB", sign_count=0)
    db.add(record)
    db.commit()
    db.refresh(record)

    webauthn_service.delete_credential(db, record.id)

    assert db.query(WebauthnCredential).count() == 0
