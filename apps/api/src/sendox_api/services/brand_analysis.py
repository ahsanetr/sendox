"""Read a brand's own data and write down what it says about them (M7 FE-4).

The merchant's five answers are short and authoritative. This is the other
half: what the catalogue, the storefront copy and the order history imply,
which is often more specific than anything a busy person types into a form.

Three decisions shape everything here.

**Evidence, not assertions.** Every claim the model makes must name the
products or pages it came from. An unsourced conclusion cannot be argued with,
and the merchant is the only one who knows whether it is true.

**Say what was missing.** Shopify withholds customers and orders from apps
without protected-data approval, so most analyses run on the catalogue alone.
A thin result for that reason is fine; a thin result that looks confident is
not, so the gaps are recorded alongside the findings.

**The prompt is kept.** When a conclusion is wrong, the first question is what
the model was actually given, and reconstructing it later from the data as it
stands today answers a different question.
"""

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from sendox_api.clients import claude
from sendox_api.config import Settings
from sendox_api.models import BrandAnalysis, BrandPage, BrandProfile, Contact, Product
from sendox_api.models.brand_analysis import next_version

# How much of each source reaches the prompt. A development store has 17
# products; a real one has thousands, and the honest options are to sample or
# to lie about having read everything. These caps are the sample, and
# `sources` records what was left out.
MAX_PRODUCTS = 60
MAX_PAGES = 25
MAX_PAGE_CHARS = 2_000
MAX_CONTACTS = 200


@dataclass
class AnalysisInputs:
    """Everything the model will see, and what we could not give it."""

    products: list[dict[str, Any]] = field(default_factory=list)
    pages: list[dict[str, Any]] = field(default_factory=list)
    profile: dict[str, Any] = field(default_factory=dict)
    contacts: int = 0
    orders: int = 0
    totals: dict[str, int] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.products and not self.pages


def gather(session: Session, tenant_id: uuid.UUID) -> AnalysisInputs:
    """Collect what this workspace actually has, and note what it does not."""
    inputs = AnalysisInputs()

    products = list(session.scalars(select(Product).order_by(Product.title)))
    inputs.totals["products"] = len(products)
    for product in products[:MAX_PRODUCTS]:
        inputs.products.append(
            {
                "title": product.title,
                "price": float(product.price) if product.price is not None else None,
                "status": product.status,
                "type": product.product_type,
                "vendor": product.vendor,
                "description": (product.description or "")[:600] or None,
            }
        )

    pages = list(
        session.scalars(
            select(BrandPage)
            .where(BrandPage.excluded_at.is_(None))
            .order_by(BrandPage.word_count.desc())
        )
    )
    inputs.totals["pages"] = len(pages)
    for page in pages[:MAX_PAGES]:
        inputs.pages.append(
            {
                "url": page.url,
                "title": page.title,
                "kind": page.kind,
                "text": page.text[:MAX_PAGE_CHARS],
            }
        )

    contacts = list(session.scalars(select(Contact).limit(MAX_CONTACTS)))
    inputs.contacts = len(contacts)
    inputs.totals["contacts"] = len(contacts)

    profile = session.scalars(select(BrandProfile)).one_or_none()
    if profile is not None:
        inputs.profile = {
            "what_you_sell": profile.what_you_sell,
            "audience": profile.audience,
            "tone": profile.tone.value if profile.tone else None,
            "never_say": profile.never_say,
            "voice_notes": profile.voice_notes,
        }

    if not inputs.products:
        inputs.missing.append("no products imported")
    if not inputs.pages:
        inputs.missing.append("no storefront pages indexed — the brand's own writing is absent")
    if not inputs.contacts:
        inputs.missing.append(
            "no customers or orders — Shopify withholds these without "
            "protected customer data approval, so buying behaviour could not be read"
        )
    if not inputs.profile:
        inputs.missing.append("the merchant has not answered the onboarding questions")

    return inputs


SCHEMA_INSTRUCTION = """Return a single JSON object, no prose around it, with exactly these keys:

{
  "positioning": "one sentence on what this brand is in the market",
  "sells": ["concrete product categories, from the catalogue"],
  "does_not_sell": ["categories conspicuously absent, if the range is clearly bounded"],
  "price_positioning": {"summary": "...", "low": 0, "high": 0, "typical": 0},
  "product_themes": ["recurring ideas across the range"],
  "audience": "who the catalogue and copy are written for",
  "tone": "how the brand writes, in a few words",
  "voice_markers": ["specific habits: sentence length, words used, words avoided"],
  "usps": ["what this brand claims sets it apart, in its own terms"],
  "vocabulary": ["words and phrases the brand actually uses"],
  "evidence": {"<any key above>": ["the product title or page URL that supports it"]},
  "contradictions": ["where the merchant's answers disagree with the data, or []"],
  "confidence": "high | medium | low",
  "confidence_reason": "why, naming what was missing"
}

Rules:
- Every claim in `evidence` must quote a product title or page URL you were
  actually given. Do not invent sources.
- If the data does not support a field, use an empty list or null. A confident
  guess is worse than an admission.
- `contradictions` is important: if the merchant says one thing and the
  catalogue shows another, say so plainly. Do not smooth it over.
- Judge only what you were given. Do not infer a brand's values from the fact
  that it sells snowboards."""


def build_prompt(inputs: AnalysisInputs) -> str:
    """Assemble the prompt, and keep it readable — it is shown to the merchant."""
    parts: list[str] = [
        "You are analysing an e-commerce brand so that a writing agent can later "
        "produce marketing emails that sound like the brand wrote them.",
        "",
        "You are given the brand's own data. Describe what it shows. Do not "
        "flatter the brand and do not fill gaps with plausible invention.",
        "",
    ]

    if inputs.profile:
        parts += [
            "## What the merchant said about themselves",
            "",
            "Treat this as authoritative about intent, but check it against the data.",
            "",
            json.dumps(inputs.profile, indent=2),
            "",
        ]

    if inputs.products:
        shown, total = len(inputs.products), inputs.totals.get("products", 0)
        suffix = f" (showing {shown} of {total})" if total > shown else ""
        parts += [f"## Catalogue{suffix}", "", json.dumps(inputs.products, indent=2), ""]

    if inputs.pages:
        shown, total = len(inputs.pages), inputs.totals.get("pages", 0)
        suffix = f" (showing {shown} of {total})" if total > shown else ""
        parts += [
            f"## The brand's own writing, taken from its storefront{suffix}",
            "",
            json.dumps(inputs.pages, indent=2),
            "",
        ]

    if inputs.missing:
        parts += [
            "## What you were NOT given",
            "",
            "Factor this into `confidence` and say so in `confidence_reason`.",
            "",
            *(f"- {gap}" for gap in inputs.missing),
            "",
        ]

    parts += ["## Output", "", SCHEMA_INSTRUCTION]
    return "\n".join(parts)


def parse_response(text: str) -> dict[str, Any]:
    """Pull the JSON object out of the reply.

    Models wrap JSON in prose or fences often enough that demanding a bare
    object means failing on output that is actually correct.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in the reply: {text[:200]}")
    parsed: dict[str, Any] = json.loads(cleaned[start : end + 1])
    return parsed


async def analyse(settings: Settings, session: Session, tenant_id: uuid.UUID) -> BrandAnalysis:
    """Generate and store a new analysis version for this workspace."""
    inputs = gather(session, tenant_id)
    if inputs.is_empty:
        raise ValueError("nothing to analyse: import a store or index its storefront first")

    prompt = build_prompt(inputs)
    completion = await claude.complete(settings, prompt=prompt)
    analysis = parse_response(completion.text)

    existing = list(session.scalars(select(BrandAnalysis.version)))
    row = BrandAnalysis(
        tenant_id=tenant_id,
        version=next_version(existing),
        analysis=analysis,
        sources={
            "counts": inputs.totals,
            "products_shown": len(inputs.products),
            "pages_shown": len(inputs.pages),
            "used_merchant_answers": bool(inputs.profile),
            "missing": inputs.missing,
        },
        prompt=prompt,
        model=completion.model,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        generated_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def latest(session: Session, tenant_id: uuid.UUID) -> BrandAnalysis | None:
    """The current analysis: newest that has not been explicitly superseded."""
    return session.scalars(
        select(BrandAnalysis)
        .where(BrandAnalysis.superseded_at.is_(None))
        .order_by(BrandAnalysis.version.desc())
    ).first()


def history(session: Session, tenant_id: uuid.UUID) -> Sequence[BrandAnalysis]:
    return session.scalars(select(BrandAnalysis).order_by(BrandAnalysis.version.desc())).all()


def restore(session: Session, tenant_id: uuid.UUID, version: int) -> BrandAnalysis | None:
    """Make an older version current by superseding everything newer.

    Supersede rather than delete: a merchant who restores v2 and then decides
    v4 was better should not have lost v4 in the process.
    """
    rows = list(session.scalars(select(BrandAnalysis)))
    target = next((row for row in rows if row.version == version), None)
    if target is None:
        return None
    now = datetime.now(UTC)
    for row in rows:
        row.superseded_at = now if row.version > version else None
    session.flush()
    return target
