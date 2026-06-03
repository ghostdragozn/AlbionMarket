from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.master_data.service import create_item, delete_item_hard, list_items

router = APIRouter(tags=["master-data"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))


@router.get("/master-data/items", response_class=HTMLResponse)
def items_page(
    request: Request,
    message: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "master_data/items.html",
        {
            "items": list_items(db),
            "message": message,
            "error": error,
        },
    )


@router.post("/master-data/items")
def create_item_action(
    code: str = Form(...),
    category: str = Form(...),
    tier: int = Form(...),
    display_name: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        create_item(db, code=code, category=category, tier=tier, display_name=display_name)
        return RedirectResponse(url="/master-data/items?message=Item%20created.", status_code=303)
    except ValueError as exc:
        return RedirectResponse(url=f"/master-data/items?error={quote(str(exc))}", status_code=303)


@router.post("/master-data/items/{item_id}/delete")
def delete_item_action(item_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        result = delete_item_hard(db, item_id)
        message = (
            f"Deleted {result['item_code']} "
            f"({result['market_listings_deleted']} market listings, "
            f"{result['warehouse_transactions_deleted']} warehouse transactions)."
        )
        return RedirectResponse(url=f"/master-data/items?message={quote(message)}", status_code=303)
    except ValueError as exc:
        return RedirectResponse(url=f"/master-data/items?error={quote(str(exc))}", status_code=303)
