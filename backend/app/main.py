from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, text

from app.api.router import api_router
from app.core.config import settings
from app.db.migrate import status as migration_status
from app.db.session import engine
from app.tasks.registry import scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    migration_status(settings.database_path)
    if settings.scheduler_enabled and not scheduler.running:
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, version=settings.data_version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    database_status = "ok"
    try:
        with Session(engine) as session:
            session.exec(text("SELECT 1")).one()
    except Exception:
        database_status = "error"

    status = "ok" if database_status == "ok" else "degraded"
    return {
        "status": status,
        "database": database_status,
        "dataVersion": settings.data_version,
    }
