from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import MarketListing
from app.modules.market.service import calculate_arbitrage_opportunities, list_market_rows, upsert_market_listing
from app.modules.master_data.service import seed_reference_data


def build_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    seed_reference_data(session)
    return session


def test_list_market_rows_returns_all_city_item_combinations() -> None:
    session = build_session()

    rows = list_market_rows(session)

    assert len(rows) == 160


def test_upsert_market_listing_creates_and_updates_listing() -> None:
    session = build_session()

    upsert_market_listing(session, city_id=1, item_id=1, unit_price=Decimal("100"), quantity=12, ratio="Cao")
    upsert_market_listing(session, city_id=1, item_id=1, unit_price=Decimal("125.55"), quantity=15, ratio="Thấp")

    listing = session.scalar(select(MarketListing).where(MarketListing.city_id == 1, MarketListing.item_id == 1))
    assert listing is not None
    assert listing.unit_price == Decimal("125.55")
    assert listing.quantity == 15
    assert listing.ratio == "Thấp"

    row = next(row for row in list_market_rows(session) if row["city_id"] == 1 and row["item_id"] == 1)
    assert row["last_updated"] != "—"
    assert row["ratio"] == "Thấp"


def test_calculate_arbitrage_applies_tax_rate() -> None:
    session = build_session()

    upsert_market_listing(session, city_id=1, item_id=1, unit_price=Decimal("100"), quantity=10, ratio="Cao")
    upsert_market_listing(session, city_id=2, item_id=1, unit_price=Decimal("160"), quantity=8, ratio="Thấp")

    opportunities = calculate_arbitrage_opportunities(session)

    best = opportunities[0]
    assert best["source_city"] == "Fort Sterling"
    assert best["destination_city"] == "Thetford"
    assert best["source_ratio"] == "Cao"
    assert best["destination_ratio"] == "Thấp"
    assert best["item_code"] == "ORE-I"
    assert best["net_sell_price"] == Decimal("143.92")
    assert best["per_unit_profit"] == Decimal("43.92")
    assert best["roi_percent"] == Decimal("43.92")
    assert best["tradable_quantity"] == 8
    assert best["total_profit"] == Decimal("351.36")


def test_calculate_arbitrage_supports_sorting() -> None:
    session = build_session()

    upsert_market_listing(session, city_id=1, item_id=1, unit_price=Decimal("100"), quantity=10, ratio="Cao")
    upsert_market_listing(session, city_id=2, item_id=1, unit_price=Decimal("160"), quantity=8, ratio="Thấp")
    upsert_market_listing(session, city_id=1, item_id=2, unit_price=Decimal("100"), quantity=10, ratio="Trung Bình")
    upsert_market_listing(session, city_id=2, item_id=2, unit_price=Decimal("130"), quantity=10, ratio="Cao")

    opportunities = calculate_arbitrage_opportunities(session, sort_by="roi_percent", sort_order="asc")

    assert opportunities[0]["roi_percent"] <= opportunities[-1]["roi_percent"]
