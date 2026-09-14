"""API routers."""
from fastapi import APIRouter

from app.api import (
    analytics,
    auth,
    campaigns,
    conversations,
    dashboard,
    health,
    integrations,
    meetings,
    notifications,
    queue,
    setup,
    settings_api,
    vendors,
)

api_router = APIRouter()
for module in (
    health,
    auth,
    setup,
    vendors,
    campaigns,
    conversations,
    meetings,
    queue,
    notifications,
    analytics,
    settings_api,
    integrations,
    dashboard,
):
    api_router.include_router(module.router)

__all__ = ["api_router"]