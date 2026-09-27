from fastapi import APIRouter

from app.api.routes import alert_rules, assets, dashboard, funds, prices, settings, system, tasks


api_router = APIRouter(prefix="/api")
api_router.include_router(assets.router)
api_router.include_router(settings.router)
api_router.include_router(alert_rules.router)
api_router.include_router(dashboard.router)
api_router.include_router(funds.router)
api_router.include_router(system.router)
api_router.include_router(prices.router)
api_router.include_router(tasks.router)
