"""Build-status endpoint.

Serves the module manifest so the dashboard shows what is actually built rather
than what a document claims. The manifest ships with the package.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from sendox_api import __version__

router = APIRouter(prefix="/status", tags=["status"])

_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "module_status.json"


@lru_cache
def _manifest() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    return data


@router.get("/modules", summary="What is built, by release and module")
async def modules() -> dict[str, Any]:
    manifest = _manifest()

    counted = [*manifest["foundation"], *manifest["modules"]]
    tally: dict[str, int] = {}
    for item in counted:
        tally[item["status"]] = tally.get(item["status"], 0) + 1

    return {
        "api_version": __version__,
        "totals": {"items": len(counted), **tally},
        **manifest,
    }
