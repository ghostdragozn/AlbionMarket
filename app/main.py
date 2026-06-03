from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.database import SessionLocal, init_db
from app.modules.market.routes import router as market_router
from app.modules.master_data.routes import router as master_data_router
from app.modules.master_data.service import seed_cities
from app.modules.reporting.routes import router as reporting_router
from app.modules.warehouse.routes import router as warehouse_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    with SessionLocal() as db:
        seed_cities(db)
    yield


app = FastAPI(title="Albion Market Manager", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")
app.include_router(master_data_router)
app.include_router(market_router)
app.include_router(warehouse_router)
app.include_router(reporting_router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/reports", status_code=303)
