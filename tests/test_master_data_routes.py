from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models import Direction, Item, MarketListing, WarehouseTransaction
from app.modules.master_data.service import create_item, seed_cities


@pytest.fixture()
def master_data_client() -> Generator[tuple[TestClient, Session], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    session = TestingSessionLocal()
    seed_cities(session)

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client, session
    finally:
        client.close()
        app.dependency_overrides.clear()
        session.close()


def test_item_master_page_renders(master_data_client: tuple[TestClient, Session]) -> None:
    client, _ = master_data_client

    response = client.get("/master-data/items")

    assert response.status_code == 200
    assert "Item master" in response.text
    assert "Create item" in response.text


def test_item_create_supports_custom_category_and_tier(master_data_client: tuple[TestClient, Session]) -> None:
    client, session = master_data_client

    response = client.post(
        "/master-data/items",
        data={
            "code": "GEM-ALPHA",
            "category": "GEM",
            "tier": 12,
            "display_name": "Gem Alpha",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/master-data/items?message=Item%20created."

    item = session.scalar(select(Item).where(Item.code == "GEM-ALPHA"))
    assert item is not None
    assert item.category == "GEM"
    assert item.tier == 12
    assert item.display_name == "Gem Alpha"

    market_page = client.get("/market")
    reports_page = client.get("/reports")
    assert '>GEM</option>' in market_page.text
    assert '>12</option>' in market_page.text
    assert '>GEM</option>' in reports_page.text
    assert '>12</option>' in reports_page.text


def test_item_create_rejects_duplicate_code(master_data_client: tuple[TestClient, Session]) -> None:
    client, session = master_data_client
    create_item(session, code="GEM-ALPHA", category="GEM", tier=12, display_name="Gem Alpha")

    response = client.post(
        "/master-data/items",
        data={
            "code": "gem-alpha",
            "category": "OTHER",
            "tier": 1,
            "display_name": "Duplicate",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/master-data/items?error=Item%20code%20already%20exists."


def test_item_delete_hard_removes_related_market_and_warehouse_data(master_data_client: tuple[TestClient, Session]) -> None:
    client, session = master_data_client
    item = create_item(session, code="GEM-ALPHA", category="GEM", tier=12, display_name="Gem Alpha")

    session.add(MarketListing(city_id=1, item_id=item.id, unit_price=100, quantity=10000))
    session.add(
        WarehouseTransaction(
            city_id=1,
            item_id=item.id,
            direction=Direction.INBOUND,
            unit_price=50,
            quantity=10,
            note="seed",
        )
    )
    session.commit()

    response = client.post(f"/master-data/items/{item.id}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert "Deleted%20GEM-ALPHA%20%281%20market%20listings%2C%201%20warehouse%20transactions%29." in response.headers["location"]
    assert session.get(Item, item.id) is None
    assert session.scalars(select(MarketListing).where(MarketListing.item_id == item.id)).all() == []
    assert session.scalars(select(WarehouseTransaction).where(WarehouseTransaction.item_id == item.id)).all() == []
