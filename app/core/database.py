from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session

BASE_DIR = Path(__file__).resolve().parents[2]
DATABASE_URL = f"sqlite:///./albion_market.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.models import City, Item, MarketListing, WarehouseTransaction  # noqa: F401

    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    market_listing_columns = {column["name"] for column in inspector.get_columns("market_listings")}
    if "ratio" not in market_listing_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE market_listings ADD COLUMN ratio VARCHAR(20)"))
