from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import BoardColumn, Invoice


class LastColumnError(Exception):
    """Wird geworfen, wenn versucht wird, die letzte verbleibende Spalte zu loeschen."""


def list_columns(db: Session) -> list[BoardColumn]:
    return db.query(BoardColumn).order_by(BoardColumn.position.asc()).all()


def get_default_column(db: Session) -> BoardColumn | None:
    return db.query(BoardColumn).order_by(BoardColumn.position.asc()).first()


def assign_to_default_column(db: Session, invoice: Invoice) -> None:
    column = get_default_column(db)
    if column is None:
        return
    max_position = (
        db.query(func.max(Invoice.board_position)).filter(Invoice.board_column_id == column.id).scalar() or 0
    )
    invoice.board_column_id = column.id
    invoice.board_position = max_position + 1
    db.commit()


def move_invoice(db: Session, invoice: Invoice, column_id: int, position: int) -> None:
    column = db.get(BoardColumn, column_id)
    if column is None:
        raise ValueError("Spalte nicht gefunden")
    invoice.board_column_id = column.id
    invoice.board_position = position
    db.commit()


def create_column(db: Session, name: str) -> BoardColumn:
    max_position = db.query(func.max(BoardColumn.position)).scalar()
    next_position = (max_position + 1) if max_position is not None else 0
    column = BoardColumn(name=name.strip() or "Ohne Titel", position=next_position)
    db.add(column)
    db.commit()
    db.refresh(column)
    return column


def rename_column(db: Session, column_id: int, name: str) -> None:
    column = db.get(BoardColumn, column_id)
    if column is None:
        raise ValueError("Spalte nicht gefunden")
    column.name = name.strip() or column.name
    db.commit()


def delete_column(db: Session, column_id: int) -> None:
    columns = list_columns(db)
    if len(columns) <= 1:
        raise LastColumnError("Die letzte Spalte kann nicht geloescht werden")

    column = db.get(BoardColumn, column_id)
    if column is None:
        raise ValueError("Spalte nicht gefunden")

    fallback = next(c for c in columns if c.id != column_id)
    db.query(Invoice).filter(Invoice.board_column_id == column_id).update({"board_column_id": fallback.id})
    db.delete(column)
    db.commit()


def move_column(db: Session, column_id: int, direction: str) -> None:
    """direction: 'up' oder 'down' - vertauscht Position mit dem Nachbarn."""
    columns = list_columns(db)
    index = next((i for i, c in enumerate(columns) if c.id == column_id), None)
    if index is None:
        raise ValueError("Spalte nicht gefunden")

    swap_index = index - 1 if direction == "up" else index + 1
    if swap_index < 0 or swap_index >= len(columns):
        return

    columns[index].position, columns[swap_index].position = columns[swap_index].position, columns[index].position
    db.commit()
