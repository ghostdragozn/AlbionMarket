from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import CITY_SPECIAL_ITEM_CATEGORIES, TAX_RATE, ZERO_MONEY
from app.models import City, Item, MarketListing

MARKET_RATIO_OPTIONS = ("Cao", "Trung Bình", "Thấp")
RATIO_SORT_ORDER = {"": 0, None: 0, "Thấp": 1, "Trung Bình": 2, "Cao": 3}

MONEY_PLACES = Decimal("0.01")


def format_market_timestamp(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def normalize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def upsert_market_listing(
    db: Session,
    city_id: int,
    item_id: int,
    unit_price: Decimal,
    quantity: int,
    ratio: str | None = None,
) -> MarketListing:
    if unit_price < 0:
        raise ValueError("Unit price must be non-negative.")
    if quantity < 0:
        raise ValueError("Quantity must be non-negative.")
    if ratio and ratio not in MARKET_RATIO_OPTIONS:
        raise ValueError("Ratio must be Cao, Trung Bình, or Thấp.")

    listing = db.scalar(
        select(MarketListing).where(
            MarketListing.city_id == city_id,
            MarketListing.item_id == item_id,
        )
    )
    normalized_price = normalize_money(unit_price)
    normalized_ratio = ratio.strip() if ratio else None

    if listing is None:
        listing = MarketListing(
            city_id=city_id,
            item_id=item_id,
            unit_price=normalized_price,
            quantity=quantity,
            ratio=normalized_ratio,
        )
        db.add(listing)
    else:
        listing.unit_price = normalized_price
        listing.quantity = quantity
        listing.ratio = normalized_ratio

    db.commit()
    db.refresh(listing)
    return listing


def list_market_rows(
    db: Session,
    city_id: int | None = None,
    category: str | None = None,
    tier: int | None = None,
) -> list[dict[str, object]]:
    city_query = select(City).order_by(City.name)
    if city_id is not None:
        city_query = city_query.where(City.id == city_id)
    cities = db.scalars(city_query).all()

    item_query = select(Item).order_by(Item.category, Item.tier)
    if category:
        item_query = item_query.where(Item.category == category)
    if tier is not None:
        item_query = item_query.where(Item.tier == tier)
    items = db.scalars(item_query).all()

    listings = db.scalars(select(MarketListing)).all()
    listing_map = {(listing.city_id, listing.item_id): listing for listing in listings}
    special_category_map = CITY_SPECIAL_ITEM_CATEGORIES

    rows: list[dict[str, object]] = []
    for city in cities:
        city_special_category = special_category_map.get(city.name)
        for item in items:
            listing = listing_map.get((city.id, item.id))
            rows.append(
                {
                    "city_id": city.id,
                    "city_name": city.name,
                    "item_id": item.id,
                    "item_code": item.code,
                    "item_display_name": item.display_name,
                    "category": item.category,
                    "tier": item.tier,
                    "unit_price": normalize_money(listing.unit_price) if listing else ZERO_MONEY,
                    "quantity": listing.quantity if listing else 0,
                    "ratio": listing.ratio if listing and listing.ratio else "",
                    "last_updated": format_market_timestamp(listing.updated_at) if listing else "—",
                    "is_city_special_item": bool(city_special_category and item.category == city_special_category),
                }
            )

    return rows


def calculate_arbitrage_opportunities(
    db: Session,
    category: str | None = None,
    tier: int | None = None,
    sort_by: str = "total_profit",
    sort_order: str = "desc",
    roi_threshold: Decimal = Decimal("20"),
) -> list[dict[str, object]]:
    item_query = select(Item).order_by(Item.code)
    if category:
        item_query = item_query.where(Item.category == category)
    if tier is not None:
        item_query = item_query.where(Item.tier == tier)
    items = db.scalars(item_query).all()
    item_map = {item.id: item for item in items}

    listings = db.scalars(select(MarketListing)).all()
    listings_by_item: dict[int, list[MarketListing]] = defaultdict(list)
    for listing in listings:
        if listing.item_id in item_map and listing.quantity > 0 and listing.unit_price > 0:
            listings_by_item[listing.item_id].append(listing)

    opportunities: list[dict[str, object]] = []
    multiplier = Decimal("1") - TAX_RATE

    for item_id, item_listings in listings_by_item.items():
        item = item_map[item_id]
        for source in item_listings:
            for destination in item_listings:
                if source.city_id == destination.city_id:
                    continue

                buy_special_category = CITY_SPECIAL_ITEM_CATEGORIES.get(source.city.name)
                sell_special_category = CITY_SPECIAL_ITEM_CATEGORIES.get(destination.city.name)
                source_is_special = bool(buy_special_category and source.item.category == buy_special_category)
                destination_is_special = bool(sell_special_category and destination.item.category == sell_special_category)

                net_sell_price = normalize_money(destination.unit_price * multiplier)
                per_unit_profit = normalize_money(net_sell_price - source.unit_price)
                if per_unit_profit <= 0:
                    continue

                tradable_quantity = min(source.quantity, destination.quantity)
                total_profit = normalize_money(per_unit_profit * tradable_quantity)
                roi_percent = normalize_money((per_unit_profit / source.unit_price) * Decimal("100"))
                if roi_percent <= roi_threshold:
                    continue
                opportunities.append(
                    {
                        "item_code": item.code,
                        "category": item.category,
                        "tier": item.tier,
                        "source_city": source.city.name,
                        "destination_city": destination.city.name,
                        "source_ratio": source.ratio or "",
                        "destination_ratio": destination.ratio or "",
                        "source_is_city_special_item": source_is_special,
                        "destination_is_city_special_item": destination_is_special,
                        "buy_price": normalize_money(source.unit_price),
                        "sell_price": normalize_money(destination.unit_price),
                        "net_sell_price": net_sell_price,
                        "per_unit_profit": per_unit_profit,
                        "roi_percent": roi_percent,
                        "tradable_quantity": tradable_quantity,
                        "total_profit": total_profit,
                    }
                )

    reverse = sort_order != "asc"
    text_fields = {"item_code", "source_city", "destination_city"}
    ratio_fields = {"source_ratio", "destination_ratio"}
    if sort_by in text_fields:
        opportunities.sort(key=lambda row: str(row[sort_by]).lower(), reverse=reverse)
    elif sort_by in ratio_fields:
        opportunities.sort(key=lambda row: RATIO_SORT_ORDER.get(row[sort_by], 0), reverse=reverse)
    else:
        opportunities.sort(key=lambda row: row.get(sort_by, Decimal("0.00")), reverse=reverse)
    return opportunities
