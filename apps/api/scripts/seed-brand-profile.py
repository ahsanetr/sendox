"""Fill the brand onboarding answers for the development store. Development only.

The dev store carries Shopify's sample catalogue, which is snowboards from a
vendor literally called "Snowboard Vendor". These answers are written to match
that, because answers that contradict the catalogue produce worse generated copy
than no answers at all: the agent is told the brand sells one thing and shown
another.

They are a stand-in, not a claim about a real business. Replace them the moment
there is a real store, which is one run of this script with different text or
five edits in the wizard.

Run from apps/api:  uv run python scripts/seed-brand-profile.py
"""

import sys
import uuid

sys.path.insert(0, "src")

from sqlalchemy import select

from sendox_api.config import get_settings
from sendox_api.db import tenant_session
from sendox_api.models import BrandTone, Tenant
from sendox_api.services import brand_profile

ANSWERS = {
    "what_you_sell": (
        "Snowboards, and not many of them. One park board, one all-mountain board, one "
        "for powder, in the lengths that actually sell. We would rather explain which of "
        "the three is wrong for you than carry a fourth. Boards are the whole range: we "
        "do not sell outerwear, we do not sell goggles, and we are not about to start."
    ),
    "audience": (
        "People who ride fifteen to forty days a season and are replacing a board rather "
        "than buying a first one. They know what camber is, they know what they did not "
        "like about their last board, and they arrive with a specific question. Beginners "
        "are welcome but we will usually tell them to rent for a season first."
    ),
    "tone": BrandTone.DIRECT,
    "never_say": (
        "Never call a board the best or the ultimate. Never say a board suits every "
        "condition, because none of them do and saying so is how people end up on the "
        "wrong one. No countdown timers, no fake stock warnings, no 'only 2 left' unless "
        "it is literally true. Do not use the words curated, elevate, unleash or "
        "game-changer. Never promise delivery before a date we do not control. Never "
        "imply we tested a board in conditions we have not ridden it in."
    ),
    "voice_notes": (
        "Short sentences, one idea each. We name the drawback before the benefit, because "
        "the people who buy from us check. No exclamation marks and no emoji. We write "
        "'you', never 'our valued customers'. Prices are stated plainly with no "
        "decoration. Lengths and flex ratings are given as numbers, not adjectives. If we "
        "do not know an answer we say so instead of guessing. We sign off "
        "'See you up there'."
    ),
}


def main() -> int:
    settings = get_settings()

    # `tenants` carries no row-level security, so it can be listed directly;
    # everything owned by a tenant needs that tenant's context to be visible.
    from sendox_api.db import get_sessionmaker

    with get_sessionmaker(settings)() as session:
        tenants = session.execute(
            select(Tenant.id, Tenant.name).order_by(Tenant.created_at.desc())
        ).all()

    if not tenants:
        print("No workspace found. Sign up at http://localhost:3000 first.")
        return 1

    tenant_id: uuid.UUID = tenants[0][0]
    name: str = tenants[0][1]

    with tenant_session(settings, tenant_id) as session:
        profile = brand_profile.update_profile(session, tenant_id, **ANSWERS)
        complete = profile.is_complete

    print(f"Brand profile written for workspace: {name}")
    print(f"  complete: {complete}")
    for key, value in ANSWERS.items():
        shown = value.value if isinstance(value, BrandTone) else str(value)
        print(f"  {key:15} {shown[:72]}{'…' if len(shown) > 72 else ''}")
    print()
    print("Open http://localhost:3000/brand to review or edit them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
