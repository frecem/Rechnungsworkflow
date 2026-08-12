// Allgemeine UI-Verhalten, per data-Attribut im HTML angefordert.
//
// Bewusst hier statt als Inline-Handler (onclick=/onsubmit=) im Template: nur so
// kann die Content-Security-Policy ohne 'unsafe-inline' fuer Skripte auskommen,
// was ein eingeschleustes <script> wirkungslos macht.

// <form data-confirm="Text?"> - Rueckfrage vor dem Absenden
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

// <tr data-href="/ziel"> - ganze Zeile als Link
document.querySelectorAll("[data-href]").forEach((element) => {
  element.addEventListener("click", () => {
    window.location = element.dataset.href;
  });
});

// <select data-autosubmit> - Formular direkt bei Auswahl abschicken
document.querySelectorAll("[data-autosubmit]").forEach((element) => {
  element.addEventListener("change", () => element.form.submit());
});

// <button data-print> - Druckdialog oeffnen
document.querySelectorAll("[data-print]").forEach((button) => {
  button.addEventListener("click", () => window.print());
});

// <form data-noop> - Formular, das nur als Layout-Container dient
document.querySelectorAll("form[data-noop]").forEach((form) => {
  form.addEventListener("submit", (event) => event.preventDefault());
});
