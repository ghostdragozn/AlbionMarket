from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import CITY_NAMES, build_seed_items
from app.models import City, Item, MarketListing, WarehouseTransaction


def seed_cities(db: Session) -> None:
    existing_cities = {city.name for city in db.scalars(select(City)).all()}
    for city_name in CITY_NAMES:
        if city_name not in existing_cities:
            db.add(City(name=city_name))
    db.commit()


def seed_default_items(db: Session) -> None:
    existing_items = {item.code for item in db.scalars(select(Item)).all()}
    for item_data in build_seed_items():
        if item_data["code"] not in existing_items:
            db.add(
                Item(
                    code=item_data["code"],
                    category=item_data["category"],
                    tier=item_data["tier"],
                    display_name=item_data["display_name"],
                )
            )
    db.commit()


def seed_reference_data(db: Session) -> None:
    seed_cities(db)
    seed_default_items(db)


def list_items(db: Session) -> list[Item]:
    return db.scalars(select(Item).order_by(Item.category, Item.tier, Item.code)).all()


def get_item_filter_options(db: Session) -> tuple[list[str], list[int]]:
    items = list_items(db)
    categories = sorted({item.category for item in items})
    tiers = sorted({item.tier for item in items})
    return categories, tiers


def create_item(db: Session, code: str, category: str, tier: int, display_name: str) -> Item:
    normalized_code = code.strip().upper()
    normalized_category = category.strip()
    normalized_display_name = display_name.strip()

    if not normalized_code:
        raise ValueError("Code is required.")
    if not normalized_category:
        raise ValueError("Category is required.")
    if tier <= 0:
        raise ValueError("Tier must be greater than zero.")
    if not normalized_display_name:
        raise ValueError("Display name is required.")

    existing = db.scalar(select(Item).where(Item.code == normalized_code))
    if existing is not None:
        raise ValueError("Item code already exists.")

    item = Item(
        code=normalized_code,
        category=normalized_category,
        tier=tier,
        display_name=normalized_display_name,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def delete_item_hard(db: Session, item_id: int) -> dict[str, int | str]:
    item = db.get(Item, item_id)
    if item is None:
        raise ValueError("Item not found.")

    market_listings = db.scalars(select(MarketListing).where(MarketListing.item_id == item_id)).all()
    warehouse_transactions = db.scalars(
        select(WarehouseTransaction).where(WarehouseTransaction.item_id == item_id)
    ).all()

    deleted_market_count = len(market_listings)
    deleted_warehouse_count = len(warehouse_transactions)
    item_code = item.code

    for listing in market_listings:
        db.delete(listing)
    for transaction in warehouse_transactions:
        db.delete(transaction)
    db.delete(item)
    db.commit()

    return {
        "item_code": item_code,
        "market_listings_deleted": deleted_market_count,
        "warehouse_transactions_deleted": deleted_warehouse_count,
    }
