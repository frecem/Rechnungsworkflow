"""CLI-Fallback zum Zurücksetzen des Login-Passworts, falls SMTP nicht
funktioniert und der Reset-Link per E-Mail (siehe app/services/password_reset.py)
deshalb nicht ankommt. Muss direkt auf dem Server mit Zugriff auf die DB laufen.

Aufruf: python -m scripts.reset_password
"""

import getpass
import sys

from app.database import SessionLocal
from app.services.auth import hash_password
from app.services.settings_service import get_settings


def main() -> None:
    password = getpass.getpass("Neues Passwort: ")
    password_confirm = getpass.getpass("Neues Passwort bestätigen: ")

    if len(password) < 8:
        print("Passwort muss mindestens 8 Zeichen lang sein.", file=sys.stderr)
        raise SystemExit(1)
    if password != password_confirm:
        print("Passwörter stimmen nicht überein.", file=sys.stderr)
        raise SystemExit(1)

    db = SessionLocal()
    try:
        settings = get_settings(db)
        settings.admin_password_hash = hash_password(password)
        settings.password_reset_token = None
        settings.password_reset_token_expires_at = None
        db.commit()
    finally:
        db.close()

    print("Passwort wurde zurückgesetzt.")


if __name__ == "__main__":
    main()
