from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import City
from app.modules.master_data.service import get_item_filter_options
from app.modules.reporting.service import build_reports_context

router = APIRouter(tags=["reports"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[2] / "templates"))


def parse_optional_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


@router.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    city_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    tier: str | None = Query(default=None),
    roi_threshold: str | None = Query(default="20"),
    sort_by: str = Query(default="total_profit"),
    sort_order: str = Query(default="desc"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    selected_city_id = parse_optional_int(city_id)
    selected_tier = parse_optional_int(tier)
    selected_roi_threshold = Decimal(roi_threshold) if roi_threshold not in (None, "") else Decimal("20")
    cities = db.scalars(select(City).order_by(City.name)).all()
    categories, tiers = get_item_filter_options(db)
    context = build_reports_context(
        db,
        city_id=selected_city_id,
        category=category,
        tier=selected_tier,
        arbitrage_sort_by=sort_by,
        arbitrage_sort_order=sort_order,
        roi_threshold=selected_roi_threshold,
    )

    def build_sort_url(column: str) -> str:
        next_order = "asc" if sort_by != column or sort_order == "desc" else "desc"
        params: dict[str, str | int] = {"sort_by": column, "sort_order": next_order}
        if selected_city_id is not None:
            params["city_id"] = selected_city_id
        if category:
            params["category"] = category
        if selected_tier is not None:
            params["tier"] = selected_tier
        params["roi_threshold"] = selected_roi_threshold
        return f"/reports?{urlencode(params)}"
    context.update(
        {
            "request": request,
            "cities": cities,
            "categories": categories,
            "tiers": tiers,
            "selected_city_id": selected_city_id,
            "selected_category": category,
            "selected_tier": selected_tier,
            "roi_threshold": selected_roi_threshold,
            "arbitrage_sort_by": sort_by,
            "arbitrage_sort_order": sort_order,
            "build_sort_url": build_sort_url,
        }
    )
    return templates.TemplateResponse(request, "reports/index.html", context)
