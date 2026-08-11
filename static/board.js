document.addEventListener("dragstart", (e) => {
  const card = e.target.closest(".board-card");
  if (!card) return;
  e.dataTransfer.setData("text/plain", card.dataset.invoiceId);
  card.classList.add("dragging");
});

document.addEventListener("dragend", (e) => {
  const card = e.target.closest(".board-card");
  if (card) card.classList.remove("dragging");
});

function getDragAfterElement(container, y) {
  const draggableElements = [...container.querySelectorAll(".board-card:not(.dragging)")];
  return draggableElements.reduce(
    (closest, child) => {
      const box = child.getBoundingClientRect();
      const offset = y - box.top - box.height / 2;
      if (offset < 0 && offset > closest.offset) {
        return { offset, element: child };
      }
      return closest;
    },
    { offset: Number.NEGATIVE_INFINITY, element: null }
  ).element;
}

document.querySelectorAll(".board-column-body").forEach((columnBody) => {
  columnBody.addEventListener("dragover", (e) => {
    e.preventDefault();
    const dragging = document.querySelector(".board-card.dragging");
    if (!dragging) return;
    const afterElement = getDragAfterElement(columnBody, e.clientY);
    if (afterElement == null) {
      columnBody.appendChild(dragging);
    } else {
      columnBody.insertBefore(dragging, afterElement);
    }
  });

  columnBody.addEventListener("drop", (e) => {
    e.preventDefault();
    const dragging = document.querySelector(".board-card.dragging");
    if (!dragging) return;

    const columnId = columnBody.closest(".board-column").dataset.columnId;
    const cards = [...columnBody.querySelectorAll(".board-card")];
    const position = cards.indexOf(dragging);

    fetch("/board/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        invoice_id: parseInt(dragging.dataset.invoiceId, 10),
        column_id: parseInt(columnId, 10),
        position,
      }),
    });
  });
});
