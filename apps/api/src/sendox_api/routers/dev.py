"""Development-only capability checks.

These prove the wiring the dashboard reports on: that the API can enqueue work a
worker actually executes, and that it can reach the MJML sidecar. Never mounted
when ENV is production.
"""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from sendox_api.clients.mjml import MjmlRenderError, render
from sendox_api.dependencies import SettingsDep

router = APIRouter(prefix="/dev", tags=["dev"])

SAMPLE_MJML = """<mjml>
  <mj-body background-color="#f4f4f5">
    <mj-section background-color="#ffffff" padding="24px">
      <mj-column>
        <mj-text font-size="20px" font-weight="700">Your cart misses you</mj-text>
        <mj-text font-size="14px" color="#52525b">
          Still thinking it over? Your items are waiting.
        </mj-text>
        <mj-button background-color="#111827" href="https://example.test/cart">
          Complete checkout
        </mj-button>
      </mj-column>
    </mj-section>
  </mj-body>
</mjml>"""


class RenderRequest(BaseModel):
    mjml: str = Field(default=SAMPLE_MJML, description="MJML source; defaults to a sample email")
    minify: bool = False


class TaskAccepted(BaseModel):
    task_id: str
    state: str


@router.post("/tasks/ping", response_model=TaskAccepted, summary="Enqueue a Celery round-trip")
async def enqueue_ping(payload: str = "pong") -> TaskAccepted:
    # Imported here so the module does not require a broker at import time.
    from sendox_api.tasks import ping

    result = ping.delay(payload)
    return TaskAccepted(task_id=result.id, state=result.state)


@router.get("/tasks/{task_id}", summary="Poll a Celery task")
async def task_result(task_id: str) -> dict[str, Any]:
    from sendox_api.worker import celery_app

    async_result = celery_app.AsyncResult(task_id)
    ready = bool(async_result.ready())

    return {
        "task_id": task_id,
        "state": str(async_result.state),
        "ready": ready,
        "result": async_result.result if ready and async_result.successful() else None,
    }


@router.post("/mjml/render", summary="Compile MJML through the sidecar")
async def render_mjml(request: RenderRequest, settings: SettingsDep) -> dict[str, Any]:
    try:
        result = await render(settings, request.mjml, minify=request.minify)
    except MjmlRenderError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return {
        "ok": result.ok,
        "errors": result.errors,
        "html_bytes": len(result.html),
        "responsive": "@media" in result.html,
        "html": result.html,
    }
