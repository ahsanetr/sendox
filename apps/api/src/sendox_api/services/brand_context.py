"""The single brand context the writing agents consume.

Two sources feed it: what the merchant said, and what an agent concluded from
their data. This composes them into one object so an agent asks one question
instead of three, which was the point of combining them.

What it does **not** do is blend them into anonymous prose. Every field records
which source it came from, because the first question about a bad email is
"did the brand tell us that, or did we infer it?" — and a merged blob answers
neither. Precedence is fixed and stated: the merchant wins. They know their
business; the analysis is reading tea leaves from a product catalogue.

Where the two disagree, both are kept and the disagreement is surfaced rather
than resolved. A contradiction is information: it usually means the catalogue
has drifted from how the owner thinks about the brand, and only they can say
which one is out of date.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sendox_api.models import BrandProfile
from sendox_api.services import brand_analysis

# Where a value came from. Carried on every composed field.
MERCHANT = "merchant"
ANALYSIS = "analysis"


def _sourced(value: Any, source: str) -> dict[str, Any] | None:
    """A value with its provenance, or nothing if there is no value."""
    if value in (None, "", [], {}):
        return None
    return {"value": value, "source": source}


def compose(session: Session, tenant_id: uuid.UUID) -> dict[str, Any]:
    """Build the brand context for this workspace.

    Returns a dict shaped for a prompt, not for a UI: the agents read it, and
    the Brand screen renders the same thing with the sources made visible.
    """
    profile = session.scalars(select(BrandProfile)).one_or_none()
    analysis_row = brand_analysis.latest(session, tenant_id)
    derived: dict[str, Any] = analysis_row.analysis if analysis_row else {}

    context: dict[str, Any] = {"fields": {}, "rules": {}, "meta": {}}
    fields = context["fields"]

    def put(key: str, merchant_value: Any, analysis_key: str | None = None) -> None:
        """Merchant first, analysis as fallback, disagreement recorded."""
        analysis_value = derived.get(analysis_key or key)
        chosen = _sourced(merchant_value, MERCHANT) or _sourced(analysis_value, ANALYSIS)
        if chosen is None:
            return
        fields[key] = chosen
        # Both present and materially different: keep the other one visible.
        if merchant_value and analysis_value and chosen["source"] == MERCHANT:
            fields[key]["also_observed"] = analysis_value

    put("what_you_sell", profile.what_you_sell if profile else None, "positioning")
    put("audience", profile.audience if profile else None, "audience")
    put("tone", (profile.tone.value if profile and profile.tone else None), "tone")

    # These have no merchant equivalent: they are only ever observed.
    for key in (
        "sells",
        "does_not_sell",
        "price_positioning",
        "product_themes",
        "usps",
        "voice_markers",
        "vocabulary",
    ):
        sourced = _sourced(derived.get(key), ANALYSIS)
        if sourced is not None:
            fields[key] = sourced

    # Rules the agent must obey rather than consider. Only the merchant sets
    # these: an inferred prohibition is a guess, and a guess about what a brand
    # refuses to say is not something to act on.
    if profile and profile.never_say:
        context["rules"]["never_say"] = profile.never_say
    if profile and profile.voice_notes:
        context["rules"]["voice_notes"] = profile.voice_notes

    context["meta"] = {
        "has_merchant_answers": bool(profile and profile.is_complete),
        "has_analysis": analysis_row is not None,
        "analysis_version": analysis_row.version if analysis_row else None,
        "analysis_confidence": derived.get("confidence"),
        "analysis_gaps": (analysis_row.sources or {}).get("missing", [])
        if analysis_row
        else ["no analysis has been generated"],
        "contradictions": derived.get("contradictions") or [],
        "evidence": derived.get("evidence") or {},
    }
    return context


def as_prompt_block(context: dict[str, Any]) -> str:
    """Render the context as text for a prompt.

    Sources are kept in the rendering. An agent told that the audience is
    *observed* rather than *stated* should weigh it differently, and stripping
    that distinction to save tokens would be a false economy.
    """
    lines: list[str] = ["# Brand context", ""]

    for key, entry in context.get("fields", {}).items():
        label = key.replace("_", " ").capitalize()
        marker = (
            "stated by the brand" if entry["source"] == MERCHANT else "observed from their data"
        )
        value = entry["value"]
        rendered = ", ".join(map(str, value)) if isinstance(value, list) else value
        lines.append(f"**{label}** ({marker}): {rendered}")
        if "also_observed" in entry:
            lines.append(f"  - but their data suggests: {entry['also_observed']}")
    lines.append("")

    rules = context.get("rules", {})
    if rules:
        lines += ["## Rules set by the brand. These are not suggestions.", ""]
        if "never_say" in rules:
            lines.append(f"Never say: {rules['never_say']}")
        if "voice_notes" in rules:
            lines.append(f"How they write: {rules['voice_notes']}")
        lines.append("")

    meta = context.get("meta", {})
    if meta.get("contradictions"):
        lines += [
            "## Noted disagreements between what the brand says and what its data shows",
            "",
            *(f"- {item}" for item in meta["contradictions"]),
            "",
        ]
    if meta.get("analysis_gaps"):
        lines += [
            "## What was not available when this was assembled",
            "",
            *(f"- {gap}" for gap in meta["analysis_gaps"]),
            "",
        ]
    return "\n".join(lines).strip()
