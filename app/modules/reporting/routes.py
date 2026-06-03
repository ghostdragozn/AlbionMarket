from pathlib import Path

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
    db: Session = Depends(get_db),
) -> HTMLResponse:
    selected_city_id = parse_optional_int(city_id)
    selected_tier = parse_optional_int(tier)
    cities = db.scalars(select(City).order_by(City.name)).all()
    categories, tiers = get_item_filter_options(db)
    context = build_reports_context(db, city_id=selected_city_id, category=category, tier=selected_tier)
    context.update(
        {
            "request": request,
            "cities": cities,
            "categories": categories,
            "tiers": tiers,
            "selected_city_id": selected_city_id,
            "selected_category": category,
            "selected_tier": selected_tier,
        }
    )
    return templates.TemplateResponse(request, "reports/index.html", context)
