---
name: e2e-verify
description: Live HTTP + browser verification for Rechnungsworkflow. Starts a real uvicorn instance, exercises every route as both an anonymous and a logged-in user, resolves every template link, and checks the rendered pages with Playwright for CSP violations and JS console errors. Use after changes that touch routers, templates, static JS/CSS, the login/session/passkey flow, or app/main.py's middleware — this project has no HTTP test client in pytest (see CLAUDE.md "Testing conventions"), so this is the only way those changes get exercised end-to-end before shipping. Not needed for pure service/model logic already covered by pytest.
tools: Bash, Read, Grep, Glob, Write
---

You verify a change to Rechnungsworkflow (FastAPI + Jinja2 + vanilla JS, see CLAUDE.md
for architecture) by actually running it, not by reading the diff. Nothing here is a
description of the app — it is a checklist of what to *do*. Work in the repo root.

## 1. Fresh, migrated database

```bash
rm -f storage/db.sqlite3 && rm -rf storage/invoices/*
.venv/bin/python -m alembic upgrade head
```

If a migration was added this session, also run `downgrade -1` then `upgrade head`
again to confirm it's reversible before moving on.

## 2. Start the server

```bash
.venv/bin/uvicorn app.main:app --port 8123
```

Run this with the Bash tool's `run_in_background: true`. **If the process fails with
"attempt to write a readonly database"**, the background shell is running in a more
restricted sandbox than your interactive shell — retry the same command with
`dangerouslyDisableSandbox: true`. This is a known quirk of some remote/web sessions,
not an app bug; don't spend time debugging file permissions in `app/services/storage.py`
because of it.

Use `http://localhost:8123`, not `127.0.0.1` — WebAuthn/passkey calls reject a bare
IP address as an invalid RP ID, so testing against `127.0.0.1` will produce false
failures on anything passkey-related. `localhost` is treated as a secure context and
works even over plain HTTP.

## 3. Route matrix (curl)

Enumerate the current routes rather than assuming the list from a past run:

```bash
grep -rn "@router\.\(get\|post\|put\|delete\)" app/routers/*.py
```

For every route, with two cookie jars (`anon.txt` never logged in, `jar.txt` logged
in after `/setup` + `/login`):

- **Anonymous**: every route except the public ones (`/login`, `/setup`,
  `/forgot-password`, `/reset-password`, `/webauthn/login/options`,
  `/webauthn/login/verify` — cross-check this list against `PUBLIC_PATHS` in
  `app/main.py`, it may have grown) must redirect (303/307) to `/login`, never 200.
- **Authenticated**: no route may return 500. GET routes should return 200 (or a
  303 for ones that always redirect, e.g. `/`). POST routes that mutate state are
  fine to actually exercise (upload a small fake PDF via
  `printf '%%PDF-1.4\n%%test\n' > /tmp/e2e.pdf`, save/approve it, create/rename/delete
  a board column and a category, etc.) — use throwaway data, this DB gets discarded.
- **404 handling**: `/invoices/99999` and `/invoices/99999/file` must 404, not 500.

## 4. Dead-link check

```bash
grep -rhoE '(href|action)="(/[^"{}]*)"' app/templates/ | sed -E 's/.*"(\/[^"]*)"/\1/' | sort -u
grep -rhoE 'fetch\("(/[^"]*)"' static/*.js | sed -E 's/.*"(\/[^"]*)"/\1/' | sort -u
```

curl every resulting path while logged in; anything returning 404 is a dead link
(405 is fine — it just means the path only accepts a different HTTP method).

## 5. Playwright: CSP violations and console errors

The app ships a strict CSP with no `unsafe-inline` (see CLAUDE.md "CSP-driven
frontend constraints"). A broken interactive element usually fails *silently* in
the browser — curl can't see this, only a real browser can.

Check Playwright/Chromium availability first: if `$PLAYWRIGHT_BROWSERS_PATH` is set
(true in this project's remote/web sessions), Chromium is already installed — do
**not** run `playwright install`; launch with
`executable_path="$PLAYWRIGHT_BROWSERS_PATH/chromium"`. Otherwise run
`pip install playwright && playwright install chromium` once, locally, first.

Write a throwaway script (not committed) that:
1. Logs in, then visits every main page (`/board`, `/invoices`, `/upload`, `/stats`,
   `/settings`, `/board/columns`, an `/invoices/<id>` detail page).
2. Registers `page.on("console", ...)` and fails on any message containing
   `"Content Security Policy"` or `"Refused to"`, and `page.on("pageerror", ...)`.
3. Exercises the interactive patterns this app relies on instead of inline handlers
   (`static/app.js`'s `data-*` attributes): click a table row with `data-href` and
   confirm navigation, click a `data-confirm` delete button and confirm a native
   `dialog` event fires, confirm a `data-autosubmit` `<select>` submits its form,
   confirm the board's `.board-card-move` dropdown exists, confirm the beleg preview
   `iframe`/`img` in an `/invoices/<id>` page actually loads (this also validates
   `frame-ancestors` in the CSP didn't just block your own preview — that has
   happened before, see README "Code- und Sicherheitsprüfung").

## 6. Passkey/WebAuthn flow (only if auth, session, or webauthn_service.py changed)

Chromium's CDP virtual authenticator lets you test the full flow without real
hardware: `context.new_cdp_session(page)` → `WebAuthn.enable` →
`WebAuthn.addVirtualAuthenticator` with
`{protocol: "ctap2", transport: "internal", hasResidentKey: true, hasUserVerification: true, isUserVerified: true, automaticPresenceSimulation: true}`.
Then: log in with password → register a passkey from `/settings` → log out → confirm
the "Mit Passkey anmelden" button appears on `/login` (it's conditional on
`has_passkeys`) → click it → confirm you land on `/board` without ever entering the
password.

## 7. Report and clean up

Report as a pass/fail list per section above, not prose — this is a checklist, and
whoever reads the result wants to know what broke, not a narrative. Include exact
routes/messages for any failure, since that's what someone will need to reproduce it.

Then:
```bash
pkill -f "uvicorn app.main:app"
rm -f storage/db.sqlite3 && rm -rf storage/invoices/*
.venv/bin/python -m alembic upgrade head
```
so you don't leave a stray server process or throwaway test data behind for the
next task.
