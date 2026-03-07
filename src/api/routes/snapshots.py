"""Snapshot REST endpoints backed by Redis."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.services.redis_service import RedisService


router = APIRouter(prefix="/api", tags=["snapshots"])


def get_redis_service() -> RedisService:
    from api.dependencies import get_redis_service as dependency

    return dependency()


@router.get("/metrics")
async def metrics(service: RedisService = Depends(get_redis_service)) -> dict[str, Any]:
    return await service.get_metrics()


@router.get("/traffic")
async def traffic(service: RedisService = Depends(get_redis_service)) -> list[dict[str, Any]]:
    return await service.get_traffic()


@router.get("/activities")
async def activities(service: RedisService = Depends(get_redis_service)) -> list[dict[str, Any]]:
    return await service.get_activities()


@router.get("/regions")
async def regions(service: RedisService = Depends(get_redis_service)) -> list[dict[str, Any]]:
    return await service.get_regions()


@router.get("/flows")
async def flows(service: RedisService = Depends(get_redis_service)) -> list[dict[str, Any]]:
    return await service.get_flows()


@router.get("/alerts")
async def alerts(service: RedisService = Depends(get_redis_service)) -> dict[str, Any]:
    return await service.get_alerts()


@router.get("/platform")
async def platform(service: RedisService = Depends(get_redis_service)) -> list[dict[str, Any]]:
    return await service.get_platform()


@router.get("/health")
async def health_snapshot(service: RedisService = Depends(get_redis_service)) -> dict[str, Any]:
    return await service.get_health()


@router.get("/geo")
async def geo(service: RedisService = Depends(get_redis_service)) -> dict[str, Any]:
    return await service.get_geo()
