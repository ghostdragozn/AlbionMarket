from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import City, Direction, Item
from app.modules.reporting.service import build_trade_rows
from app.modules.warehouse.service import delete_transaction_hard, list_transactions, record_transaction

router = APIRouter(tags=["warehouse"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))


@router.get("/warehouse", response_class=HTMLResponse)
def warehouse_page(
    request: Request,
    city_id: int | None = Query(default=None),
    item_id: int | None = Query(default=None),
    direction: Direction | None = Query(default=None),
    message: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    cities = db.scalars(select(City).order_by(City.name)).all()
    items = db.scalars(select(Item).order_by(Item.code)).all()
    transactions = list_transactions(db, city_id=city_id, item_id=item_id, direction=direction)
    inventory_rows = [row for row in build_trade_rows(db, city_id=city_id) if row["current_inventory"] > 0]
    return templates.TemplateResponse(
        request,
        "warehouse/index.html",
        {
            "cities": cities,
            "items": items,
            "transactions": transactions,
            "inventory_rows": inventory_rows,
            "selected_city_id": city_id,
            "selected_item_id": item_id,
            "selected_direction": direction.value if direction else None,
            "message": message,
            "error": error,
            "directions": [Direction.INBOUND, Direction.OUTBOUND],
        },
    )


@router.post("/warehouse/transactions")
def save_transaction(
    city_id: int = Form(...),
    item_id: int = Form(...),
    direction: Direction = Form(...),
    unit_price: Decimal = Form(...),
    quantity: int = Form(...),
    note: str = Form(default=""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        record_transaction(
            db,
            city_id=city_id,
            item_id=item_id,
            direction=direction,
            unit_price=unit_price,
            quantity=quantity,
            note=note,
        )
        return RedirectResponse(url="/warehouse?message=Warehouse%20transaction%20saved.", status_code=303)
    except ValueError as exc:
        return RedirectResponse(url=f"/warehouse?error={quote(str(exc))}", status_code=303)


@router.post("/warehouse/transactions/{transaction_id}/delete")
def delete_transaction(
    transaction_id: int,
    return_city_id: int | None = Form(default=None),
    return_item_id: int | None = Form(default=None),
    return_direction: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    params: dict[str, str | int] = {}
    if return_city_id is not None:
        params["city_id"] = return_city_id
    if return_item_id is not None:
        params["item_id"] = return_item_id
    if return_direction:
        params["direction"] = return_direction

    try:
        delete_transaction_hard(db, transaction_id)
        params["message"] = "Warehouse transaction deleted."
    except ValueError as exc:
        params["error"] = str(exc)

    return RedirectResponse(url=f"/warehouse?{urlencode(params)}" if params else "/warehouse", status_code=303)
