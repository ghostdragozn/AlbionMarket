from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Direction(str, Enum):
    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    market_listings: Mapped[list["MarketListing"]] = relationship(back_populates="city")
    warehouse_transactions: Mapped[list["WarehouseTransaction"]] = relationship(back_populates="city")


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(20), index=True)
    tier: Mapped[int] = mapped_column(Integer, index=True)
    display_name: Mapped[str] = mapped_column(String(100))

    market_listings: Mapped[list["MarketListing"]] = relationship(back_populates="item")
    warehouse_transactions: Mapped[list["WarehouseTransaction"]] = relationship(back_populates="item")


class MarketListing(Base):
    __tablename__ = "market_listings"
    __table_args__ = (UniqueConstraint("city_id", "item_id", name="uq_market_listing_city_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    quantity: Mapped[int] = mapped_column(Integer)
    ratio: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now().astimezone())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now().astimezone(), onupdate=lambda: datetime.now().astimezone())

    city: Mapped[City] = relationship(back_populates="market_listings")
    item: Mapped[Item] = relationship(back_populates="market_listings")


class WarehouseTransaction(Base):
    __tablename__ = "warehouse_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), index=True)
    direction: Mapped[Direction] = mapped_column(SqlEnum(Direction), index=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    quantity: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(255), default="")
    transaction_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now().astimezone(), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now().astimezone())

    city: Mapped[City] = relationship(back_populates="warehouse_transactions")
    item: Mapped[Item] = relationship(back_populates="warehouse_transactions")
