from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Direction, WarehouseTransaction

MONEY_PLACES = Decimal("0.01")


def normalize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def get_current_inventory(db: Session, city_id: int, item_id: int) -> int:
    transactions = db.scalars(
        select(WarehouseTransaction).where(
            WarehouseTransaction.city_id == city_id,
            WarehouseTransaction.item_id == item_id,
        )
    ).all()
    quantity = 0
    for transaction in transactions:
        if transaction.direction == Direction.INBOUND:
            quantity += transaction.quantity
        else:
            quantity -= transaction.quantity
    return quantity


def record_transaction(
    db: Session,
    city_id: int,
    item_id: int,
    direction: Direction,
    unit_price: Decimal,
    quantity: int,
    note: str = "",
) -> WarehouseTransaction:
    if unit_price < 0:
        raise ValueError("Unit price must be non-negative.")
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")
    if direction == Direction.OUTBOUND and quantity > get_current_inventory(db, city_id, item_id):
        raise ValueError("Outbound quantity exceeds current inventory.")

    transaction = WarehouseTransaction(
        city_id=city_id,
        item_id=item_id,
        direction=direction,
        unit_price=normalize_money(unit_price),
        quantity=quantity,
        note=note.strip(),
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def delete_transaction_hard(db: Session, transaction_id: int) -> dict[str, object]:
    transaction = db.get(WarehouseTransaction, transaction_id)
    if transaction is None:
        raise ValueError("Warehouse transaction not found.")

    details = {
        "id": transaction.id,
        "city_name": transaction.city.name,
        "item_code": transaction.item.code,
        "direction": transaction.direction.value,
        "quantity": transaction.quantity,
    }
    db.delete(transaction)
    db.commit()
    return details


def list_transactions(
    db: Session,
    city_id: int | None = None,
    item_id: int | None = None,
    direction: Direction | None = None,
) -> list[dict[str, object]]:
    query = select(WarehouseTransaction).order_by(
        WarehouseTransaction.transaction_at.desc(),
        WarehouseTransaction.id.desc(),
    )
    if city_id is not None:
        query = query.where(WarehouseTransaction.city_id == city_id)
    if item_id is not None:
        query = query.where(WarehouseTransaction.item_id == item_id)
    if direction is not None:
        query = query.where(WarehouseTransaction.direction == direction)

    transactions = db.scalars(query).all()
    return [
        {
            "id": transaction.id,
            "city_name": transaction.city.name,
            "item_code": transaction.item.code,
            "direction": transaction.direction.value,
            "unit_price": normalize_money(transaction.unit_price),
            "quantity": transaction.quantity,
            "note": transaction.note,
            "transaction_at": transaction.transaction_at,
        }
        for transaction in transactions
    ]
