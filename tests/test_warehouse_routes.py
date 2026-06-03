from collections.abc import Generator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models import Direction, WarehouseTransaction
from app.modules.master_data.service import seed_cities, seed_default_items
from app.modules.warehouse.service import record_transaction


@pytest.fixture()
def warehouse_client() -> Generator[tuple[TestClient, Session], None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    session = TestingSessionLocal()
    seed_cities(session)
    seed_default_items(session)

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


def test_warehouse_page_renders_delete_action(warehouse_client: tuple[TestClient, Session]) -> None:
    client, session = warehouse_client
    record_transaction(session, city_id=1, item_id=1, direction=Direction.INBOUND, unit_price=Decimal("100"), quantity=10)

    response = client.get("/warehouse")

    assert response.status_code == 200
    assert "Actions" in response.text
    assert "Delete" in response.text


def test_warehouse_delete_removes_transaction_and_preserves_filters(warehouse_client: tuple[TestClient, Session]) -> None:
    client, session = warehouse_client
    transaction = record_transaction(session, city_id=1, item_id=1, direction=Direction.INBOUND, unit_price=Decimal("100"), quantity=10)

    response = client.post(
        f"/warehouse/transactions/{transaction.id}/delete",
        data={"return_city_id": 1, "return_item_id": 1, "return_direction": "INBOUND"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/warehouse?city_id=1&item_id=1&direction=INBOUND&message=Warehouse+transaction+deleted."
    assert session.get(WarehouseTransaction, transaction.id) is None


def test_warehouse_delete_missing_transaction_returns_error(warehouse_client: tuple[TestClient, Session]) -> None:
    client, _ = warehouse_client

    response = client.post("/warehouse/transactions/999/delete", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/warehouse?error=Warehouse+transaction+not+found."
