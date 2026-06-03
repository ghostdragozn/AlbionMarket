from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import City
from app.modules.market.service import MARKET_RATIO_OPTIONS, format_market_timestamp, list_market_rows, upsert_market_listing
from app.modules.master_data.service import get_item_filter_options

router = APIRouter(tags=["market"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))


def parse_optional_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


@router.get("/market", response_class=HTMLResponse)
def market_page(
    request: Request,
    city_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    tier: str | None = Query(default=None),
    message: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    selected_city_id = parse_optional_int(city_id)
    selected_tier = parse_optional_int(tier)
    cities = db.scalars(select(City).order_by(City.name)).all()
    categories, tiers = get_item_filter_options(db)
    rows = list_market_rows(db, city_id=selected_city_id, category=category, tier=selected_tier)
    return templates.TemplateResponse(
        request,
        "market/index.html",
        {
            "cities": cities,
            "rows": rows,
            "categories": categories,
            "tiers": tiers,
            "ratio_options": MARKET_RATIO_OPTIONS,
            "selected_city_id": selected_city_id,
            "selected_category": category,
            "selected_tier": selected_tier,
            "message": message,
            "error": error,
        },
    )


@router.post("/market/listings")
def save_market_listing(
    request: Request,
    city_id: int = Form(...),
    item_id: int = Form(...),
    unit_price: Decimal = Form(...),
    quantity: int = Form(default=10000),
    ratio: str | None = Form(default=None),
    return_city_id: int | None = Form(default=None),
    return_category: str | None = Form(default=None),
    return_tier: int | None = Form(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    params: dict[str, str | int] = {}
    if return_city_id is not None:
        params["city_id"] = return_city_id
    if return_category:
        params["category"] = return_category
    if return_tier is not None:
        params["tier"] = return_tier

    try:
        listing = upsert_market_listing(
            db,
            city_id=city_id,
            item_id=item_id,
            unit_price=unit_price,
            quantity=quantity,
            ratio=ratio,
        )
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JSONResponse(
                {
                    "ok": True,
                    "message": "Market listing saved.",
                    "listing": {
                        "city_id": listing.city_id,
                        "item_id": listing.item_id,
                        "unit_price": f"{listing.unit_price:.2f}",
                        "quantity": listing.quantity,
                        "ratio": listing.ratio or "",
                        "last_updated": format_market_timestamp(listing.updated_at),
                    },
                }
            )
        params["message"] = "Market listing saved."
    except ValueError as exc:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        params["error"] = str(exc)

    return RedirectResponse(url=f"/market?{urlencode(params)}" if params else "/market", status_code=303)
