"""Liveness and readiness endpoints."""

from fastapi import APIRouter, Response, status

from sendox_api import __version__
from sendox_api.dependencies import SettingsDep
from sendox_api.health import run_readiness_probes

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", summary="Liveness — is the process up?")
async def live() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/ready", summary="Readiness — is every backing service reachable?")
async def ready(response: Response, settings: SettingsDep) -> dict[str, object]:
    results = await run_readiness_probes(settings)
    all_ok = all(result.status == "ok" for result in results)

    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if all_ok else "degraded",
        "version": __version__,
        "env": settings.env,
        "checks": {result.name: result.as_dict() for result in results},
    }
