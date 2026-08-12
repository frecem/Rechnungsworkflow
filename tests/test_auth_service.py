from app.services import auth


class FakeConnection:
    def __init__(self):
        self.session = {}


def test_start_session_short_sets_authenticated_and_expiry():
    conn = FakeConnection()
    auth.start_session(conn, remember=False)
    assert conn.session["authenticated"] is True
    assert "auth_expires_at" in conn.session


def test_session_is_valid_true_right_after_login():
    conn = FakeConnection()
    auth.start_session(conn, remember=False)
    assert auth.session_is_valid(conn) is True


def test_session_is_valid_true_for_remembered_session():
    conn = FakeConnection()
    auth.start_session(conn, remember=True)
    assert auth.session_is_valid(conn) is True
    # Remembered sessions must last noticeably longer than short ones.
    remember_conn = conn
    short_conn = FakeConnection()
    auth.start_session(short_conn, remember=False)
    assert remember_conn.session["auth_expires_at"] > short_conn.session["auth_expires_at"]


def test_session_is_valid_false_when_not_authenticated():
    conn = FakeConnection()
    assert auth.session_is_valid(conn) is False


def test_session_is_valid_false_and_clears_session_when_expired():
    conn = FakeConnection()
    auth.start_session(conn, remember=False)
    conn.session["auth_expires_at"] = 0  # weit in der Vergangenheit

    assert auth.session_is_valid(conn) is False
    assert conn.session == {}


def test_hash_and_verify_password_roundtrip():
    hashed = auth.hash_password("supersecret1")
    assert auth.verify_password("supersecret1", hashed) is True
    assert auth.verify_password("wrong", hashed) is False
