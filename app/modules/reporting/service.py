from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import TAX_RATE, ZERO_MONEY
from app.models import City, Direction, Item, WarehouseTransaction
from app.modules.market.service import calculate_arbitrage_opportunities

MONEY_PLACES = Decimal("0.01")


def normalize_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def build_trade_rows(
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
    item_ids = {item.id for item in items}

    transactions = db.scalars(select(WarehouseTransaction)).all()
    aggregates: dict[tuple[int, int], dict[str, Decimal | int]] = defaultdict(
        lambda: {
            "inbound_quantity": 0,
            "inbound_value": ZERO_MONEY,
            "outbound_quantity": 0,
            "outbound_value": ZERO_MONEY,
        }
    )

    for transaction in transactions:
        if transaction.item_id not in item_ids:
            continue
        if city_id is not None and transaction.city_id != city_id:
            continue

        aggregate = aggregates[(transaction.city_id, transaction.item_id)]
        value = normalize_money(transaction.unit_price * transaction.quantity)
        if transaction.direction == Direction.INBOUND:
            aggregate["inbound_quantity"] += transaction.quantity
            aggregate["inbound_value"] = normalize_money(aggregate["inbound_value"] + value)
        else:
            aggregate["outbound_quantity"] += transaction.quantity
            aggregate["outbound_value"] = normalize_money(aggregate["outbound_value"] + value)

    rows: list[dict[str, object]] = []
    net_multiplier = Decimal("1") - TAX_RATE
    for city in cities:
        for item in items:
            aggregate = aggregates[(city.id, item.id)]
            inbound_quantity = int(aggregate["inbound_quantity"])
            outbound_quantity = int(aggregate["outbound_quantity"])
            inbound_value = normalize_money(aggregate["inbound_value"])
            outbound_value = normalize_money(aggregate["outbound_value"])
            avg_import_price = normalize_money(inbound_value / inbound_quantity) if inbound_quantity else ZERO_MONEY
            avg_export_price = normalize_money(outbound_value / outbound_quantity) if outbound_quantity else ZERO_MONEY
            net_profit = normalize_money((outbound_value * net_multiplier) - inbound_value)
            rows.append(
                {
                    "city_id": city.id,
                    "city_name": city.name,
                    "item_id": item.id,
                    "item_code": item.code,
                    "category": item.category,
                    "tier": item.tier,
                    "imported_quantity": inbound_quantity,
                    "imported_value": inbound_value,
                    "avg_import_price": avg_import_price,
                    "exported_quantity": outbound_quantity,
                    "exported_value": outbound_value,
                    "avg_export_price": avg_export_price,
                    "current_inventory": inbound_quantity - outbound_quantity,
                    "net_profit": net_profit,
                }
            )
    return rows


def build_city_profit_rows(trade_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, Decimal] = defaultdict(lambda: ZERO_MONEY)
    for row in trade_rows:
        grouped[row["city_name"]] = normalize_money(grouped[row["city_name"]] + row["net_profit"])
    results = [{"city_name": city_name, "net_profit": net_profit} for city_name, net_profit in grouped.items()]
    results.sort(key=lambda row: row["city_name"])
    return results


def build_item_profit_rows(trade_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, Decimal] = defaultdict(lambda: ZERO_MONEY)
    for row in trade_rows:
        grouped[row["item_code"]] = normalize_money(grouped[row["item_code"]] + row["net_profit"])
    results = [{"item_code": item_code, "net_profit": net_profit} for item_code, net_profit in grouped.items()]
    results.sort(key=lambda row: row["item_code"])
    return results


def get_overall_profit(trade_rows: list[dict[str, object]]) -> Decimal:
    profit = ZERO_MONEY
    for row in trade_rows:
        profit = normalize_money(profit + row["net_profit"])
    return profit


def build_reports_context(
    db: Session,
    city_id: int | None = None,
    category: str | None = None,
    tier: int | None = None,
    arbitrage_sort_by: str = "total_profit",
    arbitrage_sort_order: str = "desc",
) -> dict[str, object]:
    trade_rows = build_trade_rows(db, city_id=city_id, category=category, tier=tier)
    return {
        "trade_rows": trade_rows,
        "city_profit_rows": build_city_profit_rows(trade_rows),
        "item_profit_rows": build_item_profit_rows(trade_rows),
        "overall_profit": get_overall_profit(trade_rows),
        "arbitrage_rows": calculate_arbitrage_opportunities(
            db,
            category=category,
            tier=tier,
            sort_by=arbitrage_sort_by,
            sort_order=arbitrage_sort_order,
        ),
    }
