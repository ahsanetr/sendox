"""Brand onboarding and extracted-content endpoints (scope M6).

The split mirrors where the knowledge came from. `/brand/profile` is what the
merchant said, written by the onboarding wizard. `/brand/pages` is what the
crawler read, and is read-only apart from one decision the merchant owns:
whether a page represents them. Nothing here starts a crawl — that belongs to
the store it crawls, and lives under `/shopify/stores/{id}/index`.
"""

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from sendox_api.db import tenant_session
from sendox_api.dependencies import SettingsDep, Workspace
from sendox_api.models import BrandTone, MemberRole
from sendox_api.services import brand_analysis, brand_context, brand_profile
from sendox_api.services.errors import InsufficientRole

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/workspaces/{workspace_id}/brand", tags=["brand"])

# How much of a page to send to the list view. The full text can be thousands of
# words and the list shows twenty of them; the detail endpoint serves the rest.
PREVIEW_CHARS = 280


class ProfileIn(BaseModel):
    """A partial update: every field is optional because the wizard saves per step.

    `None` means "not part of this request". An empty string means "clear this",
    which is a different thing and has to stay distinguishable — hence no
    `min_length` on the text fields.
    """

    what_you_sell: str | None = Field(default=None, max_length=4000)
    audience: str | None = Field(default=None, max_length=4000)
    tone: BrandTone | None = None
    never_say: str | None = Field(default=None, max_length=4000)
    voice_notes: str | None = Field(default=None, max_length=4000)
    logo_url: str | None = Field(default=None, max_length=2048)
    brand_colors: list[str] | None = Field(default=None, max_length=8)


class ExclusionIn(BaseModel):
    excluded: bool


def _require_editor(workspace: Workspace, action: str) -> None:
    try:
        workspace.require(MemberRole.EDITOR)
    except InsufficientRole as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=f"{action} requires the {exc.required} role; you are {exc.actual}",
        ) from exc


@router.get("/profile", summary="The brand onboarding answers")
async def read_profile(workspace: Workspace, settings: SettingsDep) -> dict[str, Any]:
    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        profile = brand_profile.get_profile(session, workspace.tenant_id)
        if profile is None:
            # Not an error: a workspace that has not started onboarding is the
            # normal first state, and the UI needs a shape to render either way.
            return {
                "started": False,
                "complete": False,
                "what_you_sell": None,
                "audience": None,
                "tone": None,
                "never_say": None,
                "voice_notes": None,
                "logo_url": None,
                "brand_colors": [],
                "completed_at": None,
            }
        return {
            "started": True,
            "complete": profile.is_complete,
            "what_you_sell": profile.what_you_sell,
            "audience": profile.audience,
            "tone": profile.tone.value if profile.tone else None,
            "never_say": profile.never_say,
            "voice_notes": profile.voice_notes,
            "logo_url": profile.logo_url,
            "brand_colors": profile.brand_colors,
            "completed_at": profile.completed_at.isoformat() if profile.completed_at else None,
        }


@router.put("/profile", summary="Save onboarding answers")
async def save_profile(
    payload: ProfileIn, workspace: Workspace, settings: SettingsDep
) -> dict[str, Any]:
    _require_editor(workspace, "editing the brand profile")

    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        profile = brand_profile.update_profile(
            session,
            workspace.tenant_id,
            **payload.model_dump(exclude_unset=True),
        )
        result = {
            "complete": profile.is_complete,
            "completed_at": profile.completed_at.isoformat() if profile.completed_at else None,
        }
    log.info("brand.profile_saved", tenant=str(workspace.tenant_id), complete=result["complete"])
    return result


@router.get("/pages", summary="What the crawler read from the storefront")
async def list_pages(workspace: Workspace, settings: SettingsDep) -> dict[str, Any]:
    """The crawl, inspectable: every page, its word count and its images.

    This is the M6 exit criterion. Without it the only window onto what the AI
    learned is a similarity search, which can only show fragments of pages it
    already decided were relevant — exactly the wrong tool for finding the page
    that should not have been learned from.
    """
    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        pages = brand_profile.pages_for(session, workspace.tenant_id)
        rows = [
            {
                "id": str(page.id),
                "url": page.url,
                "title": page.title,
                "kind": page.kind,
                "word_count": page.word_count,
                "images": page.images,
                "included": page.is_included,
                "preview": page.text[:PREVIEW_CHARS],
                "crawled_at": page.crawled_at.isoformat(),
            }
            for page in pages
        ]
        return {
            "pages": rows,
            "counts": {
                "pages": len(pages),
                "included": sum(1 for page in pages if page.is_included),
                # Words that will actually reach the knowledge base, which is
                # the number worth showing: excluded pages are still listed but
                # contribute nothing.
                "words": sum(page.word_count for page in pages if page.is_included),
                "images": sum(len(page.images) for page in pages),
            },
        }


@router.get("/pages/{page_id}", summary="One page's full extracted text")
async def read_page(page_id: str, workspace: Workspace, settings: SettingsDep) -> dict[str, Any]:
    try:
        parsed = uuid.UUID(page_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="page not found") from exc

    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        pages = {page.id: page for page in brand_profile.pages_for(session, workspace.tenant_id)}
        page = pages.get(parsed)
        if page is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="page not found")
        return {
            "id": str(page.id),
            "url": page.url,
            "title": page.title,
            "kind": page.kind,
            "word_count": page.word_count,
            "images": page.images,
            "included": page.is_included,
            "text": page.text,
            "crawled_at": page.crawled_at.isoformat(),
        }


@router.post("/pages/{page_id}/exclusion", summary="Include or exclude a page")
async def set_exclusion(
    page_id: str,
    payload: ExclusionIn,
    workspace: Workspace,
    settings: SettingsDep,
) -> dict[str, Any]:
    """Mark a page as unrepresentative, or put it back.

    Excluding does not delete: the merchant should be able to see what they
    dropped and reverse it. The next index run skips excluded pages, so the
    change only reaches the knowledge base when they ask for a re-index — which
    is the honest behaviour, since un-embedding is not something the vector
    store can do halfway.
    """
    _require_editor(workspace, "changing which pages are used")

    try:
        parsed = uuid.UUID(page_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="page not found") from exc

    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        page = brand_profile.set_page_excluded(
            session, workspace.tenant_id, parsed, payload.excluded
        )
        if page is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="page not found")
        return {
            "id": str(page.id),
            "included": page.is_included,
            "reindex_required": True,
        }


@router.get("/analysis", summary="What the agent concluded from this brand's data")
async def read_analysis(workspace: Workspace, settings: SettingsDep) -> dict[str, Any]:
    """The current analysis, its evidence, and the prompt that produced it."""
    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        row = brand_analysis.latest(session, workspace.tenant_id)
        versions = [
            {
                "version": item.version,
                "generated_at": item.generated_at.isoformat(),
                "model": item.model,
                "current": item.superseded_at is None
                and row is not None
                and item.version == row.version,
            }
            for item in brand_analysis.history(session, workspace.tenant_id)
        ]
        if row is None:
            return {"generated": False, "versions": versions}
        return {
            "generated": True,
            "version": row.version,
            "generated_at": row.generated_at.isoformat(),
            "model": row.model,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "analysis": row.analysis,
            "sources": row.sources,
            # The prompt is deliberately returned in full. A conclusion you
            # cannot trace to its input is one you cannot argue with.
            "prompt": row.prompt,
            "versions": versions,
        }


@router.post("/analysis", summary="Analyse this brand's data")
async def start_analysis(workspace: Workspace, settings: SettingsDep) -> dict[str, Any]:
    _require_editor(workspace, "analysing the brand")

    from sendox_api.tasks import analyse_brand

    task = analyse_brand.delay(str(workspace.tenant_id))
    return {"status": "queued", "task_id": task.id}


@router.post("/analysis/{version}/restore", summary="Make an older analysis current")
async def restore_analysis(
    version: int, workspace: Workspace, settings: SettingsDep
) -> dict[str, Any]:
    """Restore rather than delete: a later version may turn out to be better."""
    _require_editor(workspace, "restoring an analysis")

    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        row = brand_analysis.restore(session, workspace.tenant_id, version)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no such version")
        return {"version": row.version, "current": True}


@router.get("/context", summary="The composed context the writing agents use")
async def read_context(workspace: Workspace, settings: SettingsDep) -> dict[str, Any]:
    """Merchant answers and analysis in one object, each field keeping its source.

    This is what the agents will actually be given, returned verbatim so that
    what the merchant reviews and what the model receives cannot drift apart.
    """
    with tenant_session(settings, workspace.tenant_id, workspace.user_id) as session:
        context = brand_context.compose(session, workspace.tenant_id)
        return {"context": context, "as_prompt": brand_context.as_prompt_block(context)}
