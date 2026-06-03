from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import Direction
from app.modules.master_data.service import seed_reference_data
from app.modules.reporting.service import build_city_profit_rows, build_trade_rows, get_overall_profit
from app.modules.warehouse.service import delete_transaction_hard, get_current_inventory, record_transaction


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


def test_record_transaction_blocks_oversell() -> None:
    session = build_session()

    record_transaction(session, city_id=1, item_id=1, direction=Direction.INBOUND, unit_price=Decimal("100"), quantity=10)

    try:
        record_transaction(session, city_id=1, item_id=1, direction=Direction.OUTBOUND, unit_price=Decimal("120"), quantity=11)
    except ValueError as exc:
        assert str(exc) == "Outbound quantity exceeds current inventory."
    else:
        raise AssertionError("Expected oversell to raise ValueError.")


def test_trade_rows_and_profit_use_taxed_outbound_value() -> None:
    session = build_session()

    record_transaction(session, city_id=1, item_id=1, direction=Direction.INBOUND, unit_price=Decimal("100"), quantity=10)
    record_transaction(session, city_id=1, item_id=1, direction=Direction.OUTBOUND, unit_price=Decimal("200"), quantity=5)

    row = next(row for row in build_trade_rows(session) if row["city_id"] == 1 and row["item_id"] == 1)

    assert row["imported_quantity"] == 10
    assert row["imported_value"] == Decimal("1000.00")
    assert row["avg_import_price"] == Decimal("100.00")
    assert row["exported_quantity"] == 5
    assert row["exported_value"] == Decimal("1000.00")
    assert row["avg_export_price"] == Decimal("200.00")
    assert row["current_inventory"] == 5
    assert row["net_profit"] == Decimal("-100.50")
    assert get_current_inventory(session, city_id=1, item_id=1) == 5


def test_profit_rolls_up_by_city_and_overall() -> None:
    session = build_session()

    record_transaction(session, city_id=1, item_id=1, direction=Direction.INBOUND, unit_price=Decimal("50"), quantity=10)
    record_transaction(session, city_id=1, item_id=1, direction=Direction.OUTBOUND, unit_price=Decimal("80"), quantity=10)
    record_transaction(session, city_id=2, item_id=1, direction=Direction.INBOUND, unit_price=Decimal("100"), quantity=4)
    record_transaction(session, city_id=2, item_id=1, direction=Direction.OUTBOUND, unit_price=Decimal("200"), quantity=4)

    trade_rows = build_trade_rows(session)
    city_rows = build_city_profit_rows(trade_rows)
    city_profit = {row["city_name"]: row["net_profit"] for row in city_rows}

    assert city_profit["Fort Sterling"] == Decimal("219.60")
    assert city_profit["Thetford"] == Decimal("319.60")
    assert get_overall_profit(trade_rows) == Decimal("539.20")


def test_delete_outbound_transaction_rewrites_inventory_and_profit() -> None:
    session = build_session()

    record_transaction(session, city_id=1, item_id=1, direction=Direction.INBOUND, unit_price=Decimal("100"), quantity=10)
    outbound = record_transaction(session, city_id=1, item_id=1, direction=Direction.OUTBOUND, unit_price=Decimal("200"), quantity=5)

    delete_transaction_hard(session, outbound.id)

    row = next(row for row in build_trade_rows(session) if row["city_id"] == 1 and row["item_id"] == 1)
    assert row["exported_quantity"] == 0
    assert row["exported_value"] == Decimal("0.00")
    assert row["current_inventory"] == 10
    assert row["net_profit"] == Decimal("-1000.00")


def test_delete_inbound_transaction_rewrites_inventory_and_profit() -> None:
    session = build_session()

    inbound = record_transaction(session, city_id=1, item_id=1, direction=Direction.INBOUND, unit_price=Decimal("100"), quantity=10)
    record_transaction(session, city_id=1, item_id=1, direction=Direction.OUTBOUND, unit_price=Decimal("200"), quantity=5)

    delete_transaction_hard(session, inbound.id)

    row = next(row for row in build_trade_rows(session) if row["city_id"] == 1 and row["item_id"] == 1)
    assert row["imported_quantity"] == 0
    assert row["imported_value"] == Decimal("0.00")
    assert row["current_inventory"] == -5
    assert row["net_profit"] == Decimal("899.50")
