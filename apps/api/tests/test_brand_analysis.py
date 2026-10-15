"""The derived brand profile, and how it combines with what the merchant said.

None of these call Claude. What is worth testing here is not whether the model
is clever — it is whether we record what it was given, keep versions
recoverable, and refuse to let an inference quietly outrank the brand owner.
"""

import json
import uuid

import pytest
import sqlalchemy
from fastapi.testclient import TestClient

from sendox_api.config import Settings
from sendox_api.db import get_sessionmaker, tenant_session
from sendox_api.models import BrandAnalysis, BrandTone
from sendox_api.models.brand_analysis import next_version
from sendox_api.services import brand_analysis, brand_context, brand_profile
from tests.helpers import first_workspace, register_and_verify

pytestmark = pytest.mark.integration


def _database_up(settings: Settings) -> bool:
    try:
        with get_sessionmaker(settings)() as session:
            session.execute(sqlalchemy.text("SELECT 1"))
        return True
    except sqlalchemy.exc.SQLAlchemyError:
        return False


@pytest.fixture(autouse=True)
def _needs_database(settings: Settings) -> None:
    if not _database_up(settings):
        pytest.skip("Postgres not running — start it with `make up` or `make up-native`")


# --------------------------------------------------------------- parsing


def test_a_fenced_json_reply_is_accepted() -> None:
    """Models wrap JSON in fences often enough that refusing it fails on
    output that is actually correct."""
    reply = '```json\n{"positioning": "a snowboard shop", "confidence": "low"}\n```'

    assert brand_analysis.parse_response(reply)["positioning"] == "a snowboard shop"


def test_json_with_prose_around_it_is_accepted() -> None:
    reply = 'Here is the analysis:\n{"confidence": "high"}\nHope that helps.'

    assert brand_analysis.parse_response(reply)["confidence"] == "high"


def test_a_reply_with_no_json_is_an_error_not_a_guess() -> None:
    with pytest.raises(ValueError, match="no JSON object"):
        brand_analysis.parse_response("I could not analyse this brand.")


# --------------------------------------------------------------- versions


def test_versions_count_up_and_are_never_reused() -> None:
    """Reusing a number makes "restore version 3" ambiguous after a restore."""
    assert next_version([]) == 1
    assert next_version([1, 2, 3]) == 4
    # Even with a gap, the next one is above the highest ever issued.
    assert next_version([1, 4]) == 5


# ------------------------------------------------------- what reaches the model


def test_the_prompt_says_what_was_missing(client: TestClient, settings: Settings) -> None:
    """A thin analysis is fine. A thin analysis that looks confident is not."""
    owner = register_and_verify(client, prefix="an", workspace_name="Empty Co")
    tenant = uuid.UUID(first_workspace(client, owner)["id"])

    with tenant_session(settings, tenant) as session:
        inputs = brand_analysis.gather(session, tenant)
        prompt = brand_analysis.build_prompt(inputs)

    assert "What you were NOT given" in prompt
    assert any("no products" in gap for gap in inputs.missing)
    assert any("protected customer data" in gap for gap in inputs.missing)


def test_an_empty_workspace_is_refused_rather_than_analysed(
    client: TestClient, settings: Settings
) -> None:
    """Calling the model with nothing to read spends money to invent a brand."""
    owner = register_and_verify(client, prefix="an", workspace_name="Empty Co")
    tenant = uuid.UUID(first_workspace(client, owner)["id"])

    with tenant_session(settings, tenant) as session:
        inputs = brand_analysis.gather(session, tenant)

    assert inputs.is_empty


# ------------------------------------------------------------- composition


def _store_analysis(settings: Settings, tenant: uuid.UUID, body: dict) -> None:
    from datetime import UTC, datetime

    with tenant_session(settings, tenant) as session:
        session.add(
            BrandAnalysis(
                tenant_id=tenant,
                version=next_version(
                    list(session.scalars(sqlalchemy.select(BrandAnalysis.version)))
                ),
                analysis=body,
                sources={"missing": []},
                prompt="(test)",
                model="test",
                generated_at=datetime.now(UTC),
            )
        )


def test_the_merchant_outranks_the_analysis(client: TestClient, settings: Settings) -> None:
    """They know their business; the analysis is reading a product catalogue."""
    owner = register_and_verify(client, prefix="an", workspace_name="Context Co")
    tenant = uuid.UUID(first_workspace(client, owner)["id"])

    with tenant_session(settings, tenant) as session:
        brand_profile.update_profile(
            session, tenant, audience="Experienced riders", tone=BrandTone.DIRECT
        )
    _store_analysis(settings, tenant, {"audience": "Anyone who likes snow"})

    with tenant_session(settings, tenant) as session:
        context = brand_context.compose(session, tenant)

    assert context["fields"]["audience"]["value"] == "Experienced riders"
    assert context["fields"]["audience"]["source"] == brand_context.MERCHANT
    # The other reading is kept rather than discarded.
    assert context["fields"]["audience"]["also_observed"] == "Anyone who likes snow"


def test_an_observation_fills_a_gap_the_merchant_left(
    client: TestClient, settings: Settings
) -> None:
    owner = register_and_verify(client, prefix="an", workspace_name="Context Co")
    tenant = uuid.UUID(first_workspace(client, owner)["id"])

    _store_analysis(settings, tenant, {"audience": "Anyone who likes snow"})

    with tenant_session(settings, tenant) as session:
        context = brand_context.compose(session, tenant)

    assert context["fields"]["audience"]["source"] == brand_context.ANALYSIS


def test_prohibitions_are_never_inferred(client: TestClient, settings: Settings) -> None:
    """A guess about what a brand refuses to say is not something to act on."""
    owner = register_and_verify(client, prefix="an", workspace_name="Context Co")
    tenant = uuid.UUID(first_workspace(client, owner)["id"])

    _store_analysis(settings, tenant, {"never_say": "do not mention price"})

    with tenant_session(settings, tenant) as session:
        context = brand_context.compose(session, tenant)

    assert "never_say" not in context["rules"]


def test_the_rendered_prompt_keeps_the_source_of_every_claim(
    client: TestClient, settings: Settings
) -> None:
    """An agent told a fact is *observed* should weigh it differently from one
    the brand stated, so stripping that to save tokens is a false economy."""
    owner = register_and_verify(client, prefix="an", workspace_name="Context Co")
    tenant = uuid.UUID(first_workspace(client, owner)["id"])

    with tenant_session(settings, tenant) as session:
        brand_profile.update_profile(session, tenant, audience="Experienced riders")
    _store_analysis(settings, tenant, {"tone": "wry"})

    with tenant_session(settings, tenant) as session:
        rendered = brand_context.as_prompt_block(brand_context.compose(session, tenant))

    assert "stated by the brand" in rendered
    assert "observed from their data" in rendered


def test_contradictions_reach_the_agent(client: TestClient, settings: Settings) -> None:
    """The disagreement is the useful part; smoothing it over loses it."""
    owner = register_and_verify(client, prefix="an", workspace_name="Context Co")
    tenant = uuid.UUID(first_workspace(client, owner)["id"])

    _store_analysis(
        settings,
        tenant,
        {"contradictions": ["Merchant says three boards; the catalogue lists eleven"]},
    )

    with tenant_session(settings, tenant) as session:
        context = brand_context.compose(session, tenant)
        rendered = brand_context.as_prompt_block(context)

    assert context["meta"]["contradictions"]
    assert "the catalogue lists eleven" in rendered


# ---------------------------------------------------------------- restore


def test_restoring_an_older_version_does_not_destroy_the_newer_one(
    client: TestClient, settings: Settings
) -> None:
    """A merchant who restores v1 and then prefers v2 must still have v2."""
    owner = register_and_verify(client, prefix="an", workspace_name="Version Co")
    tenant = uuid.UUID(first_workspace(client, owner)["id"])

    _store_analysis(settings, tenant, {"positioning": "first reading"})
    _store_analysis(settings, tenant, {"positioning": "second reading"})

    with tenant_session(settings, tenant) as session:
        assert brand_analysis.latest(session, tenant).analysis["positioning"] == ("second reading")
        brand_analysis.restore(session, tenant, 1)

    with tenant_session(settings, tenant) as session:
        assert brand_analysis.latest(session, tenant).analysis["positioning"] == ("first reading")
        assert len(brand_analysis.history(session, tenant)) == 2, "v2 was destroyed"


def test_another_workspace_cannot_read_this_analysis(
    client: TestClient, settings: Settings
) -> None:
    """It quotes the brand's own copy and carries the prompt that produced it."""
    owner = register_and_verify(client, prefix="an", workspace_name="Private Co")
    workspace = first_workspace(client, owner)["id"]
    _store_analysis(settings, uuid.UUID(workspace), {"positioning": "a trade secret"})

    outsider = register_and_verify(client, prefix="other", workspace_name="Someone Else")
    response = client.get(f"/workspaces/{workspace}/brand/analysis", headers=outsider.auth)

    assert response.status_code in (403, 404)
    assert "trade secret" not in response.text


def test_the_schema_the_model_is_asked_for_is_valid_json() -> None:
    """The instruction block is a JSON example. A typo there is invisible until
    the model copies it and parsing fails on real output."""
    block = brand_analysis.SCHEMA_INSTRUCTION
    start, end = block.find("{"), block.rfind("}")

    json.loads(block[start : end + 1])
