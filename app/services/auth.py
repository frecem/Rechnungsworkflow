from datetime import datetime, timedelta

import bcrypt
from starlette.requests import HTTPConnection

# "Angemeldet bleiben" (Login-Checkbox) haelt die Session deutlich laenger als eine
# normale Sitzung - Passkey-Logins gelten immer als "remembered" (der Passkey selbst
# ist bereits durch die Geraete-Sperre/Biometrie geschuetzt, daher kein zusaetzliches
# Reibungsmoment durch eine Checkbox noetig).
SESSION_SHORT_HOURS = 12
SESSION_REMEMBER_DAYS = 180


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def start_session(connection: HTTPConnection, remember: bool) -> None:
    ttl = timedelta(days=SESSION_REMEMBER_DAYS) if remember else timedelta(hours=SESSION_SHORT_HOURS)
    connection.session["authenticated"] = True
    connection.session["auth_expires_at"] = (datetime.utcnow() + ttl).timestamp()


def session_is_valid(connection: HTTPConnection) -> bool:
    if not connection.session.get("authenticated"):
        return False
    expires_at = connection.session.get("auth_expires_at")
    if expires_at is not None and datetime.utcnow().timestamp() > expires_at:
        connection.session.clear()
        return False
    return True
