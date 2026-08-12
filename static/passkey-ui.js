// Bedienlogik fuer Passkeys auf der Login- und der Einstellungen-Seite.
// Die eigentlichen WebAuthn-Aufrufe stehen in webauthn.js.

function setPasskeyMessage(container, text, ok) {
  const paragraph = document.createElement("p");
  paragraph.className = ok ? "info" : "warning";
  // textContent statt innerHTML: der Text stammt teils aus Server-Antworten und
  // darf unter keinen Umstaenden als HTML interpretiert werden.
  paragraph.textContent = text;
  container.replaceChildren(paragraph);
}

// --- Login-Seite -----------------------------------------------------------
const passkeyLoginBtn = document.getElementById("passkey-login-btn");
if (passkeyLoginBtn) {
  const errorEl = document.getElementById("passkey-error");
  if (!window.PublicKeyCredential) {
    passkeyLoginBtn.style.display = "none";
  } else {
    passkeyLoginBtn.addEventListener("click", async () => {
      errorEl.textContent = "";
      errorEl.classList.add("is-hidden");
      try {
        await loginWithPasskey();
        window.location.href = "/";
      } catch (err) {
        errorEl.textContent = err.message || "Passkey-Anmeldung fehlgeschlagen.";
        errorEl.classList.remove("is-hidden");
      }
    });
  }
}

// --- Einstellungen-Seite ---------------------------------------------------
const passkeyRegisterBtn = document.getElementById("passkey-register-btn");
if (passkeyRegisterBtn) {
  const messageEl = document.getElementById("passkey-message");
  if (!window.PublicKeyCredential) {
    passkeyRegisterBtn.disabled = true;
    setPasskeyMessage(messageEl, "Dieser Browser unterstützt keine Passkeys.", false);
  } else {
    passkeyRegisterBtn.addEventListener("click", async () => {
      const label = document.getElementById("passkey-label").value;
      try {
        await registerPasskey(label);
        window.location.reload();
      } catch (err) {
        setPasskeyMessage(messageEl, err.message || "Registrierung fehlgeschlagen.", false);
      }
    });
  }

  document.querySelectorAll("[data-passkey-delete]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!window.confirm("Diesen Passkey entfernen?")) return;
      await fetch(form.action, { method: "POST" });
      window.location.reload();
    });
  });
}
