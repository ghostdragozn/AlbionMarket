from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models import MarketListing
from app.modules.master_data.service import seed_reference_data


@pytest.fixture()
def market_client() -> Generator[tuple[TestClient, Session], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    session = TestingSessionLocal()
    seed_reference_data(session)

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


def test_market_page_renders_inline_inputs_and_removes_top_form(market_client: tuple[TestClient, Session]) -> None:
    client, _ = market_client

    response = client.get("/market")

    assert response.status_code == 200
    assert "Update listing" not in response.text
    assert 'action="/market/listings"' in response.text
    assert 'name="unit_price"' in response.text
    assert 'type="hidden" name="quantity" value="10000"' in response.text
    assert "city-special-item" in response.text
    assert "ORE-I" in response.text


def test_market_filters_accept_blank_all_values(market_client: tuple[TestClient, Session]) -> None:
    client, _ = market_client

    response = client.get("/market?city_id=&category=&tier=")

    assert response.status_code == 200
    assert "Market listings" in response.text


def test_market_filters_narrow_results(market_client: tuple[TestClient, Session]) -> None:
    client, _ = market_client

    response = client.get("/market?city_id=1&category=ORE&tier=1")

    assert response.status_code == 200
    assert "Fort Sterling" in response.text
    assert "ORE-I" in response.text
    assert "ORE-II" not in response.text
    assert "1 rows" in response.text


def test_market_inline_save_preserves_filters_and_updates_listing(market_client: tuple[TestClient, Session]) -> None:
    client, session = market_client

    response = client.post(
        "/market/listings",
        data={
            "city_id": 1,
            "item_id": 1,
            "return_city_id": 1,
            "return_category": "ORE",
            "return_tier": 1,
            "unit_price": "125.50",
            "ratio": "Cao",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/market?city_id=1&category=ORE&tier=1&message=Market+listing+saved."

    listing = session.scalar(select(MarketListing).where(MarketListing.city_id == 1, MarketListing.item_id == 1))
    assert listing is not None
    assert listing.unit_price == Decimal("125.50")
    assert listing.quantity == 10000
    assert listing.ratio == "Cao"


def test_market_inline_save_error_preserves_filters(market_client: tuple[TestClient, Session]) -> None:
    client, _ = market_client

    response = client.post(
        "/market/listings",
        data={
            "city_id": 1,
            "item_id": 1,
            "unit_price": "-1",
            "quantity": 7,
            "return_city_id": 1,
            "return_category": "ORE",
            "return_tier": 1,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/market?city_id=1&category=ORE&tier=1&error=Unit+price+must+be+non-negative."


def test_market_ajax_save_returns_json_and_updates_listing(market_client: tuple[TestClient, Session]) -> None:
    client, session = market_client

    response = client.post(
        "/market/listings",
        data={
            "city_id": 1,
            "item_id": 1,
            "unit_price": "150.5",
            "ratio": "Trung Bình",
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["message"] == "Market listing saved."
    assert payload["listing"]["city_id"] == 1
    assert payload["listing"]["item_id"] == 1
    assert payload["listing"]["unit_price"] == "150.50"
    assert payload["listing"]["quantity"] == 10000
    assert payload["listing"]["ratio"] == "Trung Bình"
    assert payload["listing"]["last_updated"] != "—"

    listing = session.scalar(select(MarketListing).where(MarketListing.city_id == 1, MarketListing.item_id == 1))
    assert listing is not None
    assert listing.unit_price == Decimal("150.50")
    assert listing.quantity == 10000
    assert listing.ratio == "Trung Bình"


def test_market_ajax_save_validation_error_returns_json(market_client: tuple[TestClient, Session]) -> None:
    client, _ = market_client

    response = client.post(
        "/market/listings",
        data={
            "city_id": 1,
            "item_id": 1,
            "unit_price": "-5",
            "quantity": 2,
        },
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "ok": False,
        "error": "Unit price must be non-negative.",
    }
