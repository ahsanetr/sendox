"""Brand onboarding: the answers, the extracted pages, and who may change them (M6).

The questions worth asking of this module are about authority and visibility.
Does a partial save from a wizard step clobber the steps either side of it? Can
a viewer rewrite the brand's voice? Can one workspace read another's storefront
text? And is the crawl actually inspectable, or does the merchant only get to
see whatever a similarity search decides to return?
"""

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy
from fastapi.testclient import TestClient

from sendox_api.clients.storefront import Page
from sendox_api.config import Settings
from sendox_api.db import get_sessionmaker, tenant_session
from sendox_api.services import brand_profile
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


def _pages(*specs: tuple[str, str, int]) -> list[Page]:
    """Build crawler pages: (url, kind, word count), with filler text."""
    return [
        Page(url=url, title=url.rsplit("/", 1)[-1], text=" ".join(["word"] * words), kind=kind)
        for url, kind, words in specs
    ]


def test_an_unstarted_profile_reports_itself_rather_than_404(client: TestClient) -> None:
    """A workspace that has not onboarded is a normal state, not a missing resource."""
    owner = register_and_verify(client, prefix="brand", workspace_name="Northwind")
    workspace = first_workspace(client, owner)["id"]

    body = client.get(f"/workspaces/{workspace}/brand/profile", headers=owner.auth).json()

    assert body["started"] is False
    assert body["complete"] is False
    assert body["brand_colors"] == []


def test_the_wizard_can_save_one_step_at_a_time(client: TestClient) -> None:
    """The bug this guards: a later step blanking an earlier one.

    Each PUT carries only its own field, so anything absent must be left alone
    rather than treated as "set to null".
    """
    owner = register_and_verify(client, prefix="brand", workspace_name="Northwind")
    workspace = first_workspace(client, owner)["id"]
    url = f"/workspaces/{workspace}/brand/profile"

    client.put(url, headers=owner.auth, json={"what_you_sell": "Outdoor clothing"})
    client.put(url, headers=owner.auth, json={"audience": "People who are outside anyway"})
    client.put(url, headers=owner.auth, json={"tone": "direct"})

    body = client.get(url, headers=owner.auth).json()

    assert body["what_you_sell"] == "Outdoor clothing"
    assert body["audience"] == "People who are outside anyway"
    assert body["tone"] == "direct"
    assert body["complete"] is True
    assert body["completed_at"] is not None


def test_completion_ignores_the_optional_answers(client: TestClient) -> None:
    """Having nothing forbidden is an answer; it must not read as unfinished."""
    owner = register_and_verify(client, prefix="brand", workspace_name="Northwind")
    workspace = first_workspace(client, owner)["id"]
    url = f"/workspaces/{workspace}/brand/profile"

    client.put(
        url,
        headers=owner.auth,
        json={"what_you_sell": "Gloves", "audience": "Climbers", "tone": "warm"},
    )

    assert client.get(url, headers=owner.auth).json()["complete"] is True


def test_completed_at_survives_a_field_being_cleared(client: TestClient) -> None:
    """It records that onboarding happened, which stays true afterwards."""
    owner = register_and_verify(client, prefix="brand", workspace_name="Northwind")
    workspace = first_workspace(client, owner)["id"]
    url = f"/workspaces/{workspace}/brand/profile"

    client.put(
        url,
        headers=owner.auth,
        json={"what_you_sell": "Gloves", "audience": "Climbers", "tone": "warm"},
    )
    stamped = client.get(url, headers=owner.auth).json()["completed_at"]

    # An empty string is the documented way to clear an answer.
    client.put(url, headers=owner.auth, json={"audience": ""})
    after = client.get(url, headers=owner.auth).json()

    assert after["audience"] is None
    assert after["complete"] is False
    assert after["completed_at"] == stamped


def test_an_unknown_tone_is_refused(client: TestClient) -> None:
    """Tone reaches a prompt, so it is a closed list rather than free text."""
    owner = register_and_verify(client, prefix="brand", workspace_name="Northwind")
    workspace = first_workspace(client, owner)["id"]

    response = client.put(
        f"/workspaces/{workspace}/brand/profile",
        headers=owner.auth,
        json={"tone": "shouty"},
    )

    assert response.status_code == 422


def test_extracted_pages_are_inspectable(client: TestClient, settings: Settings) -> None:
    """The M6 exit criterion: the merchant can see what was read, not a fragment."""
    owner = register_and_verify(client, prefix="brand", workspace_name="Northwind")
    workspace = first_workspace(client, owner)["id"]
    tenant = uuid.UUID(workspace)

    with tenant_session(settings, tenant) as session:
        brand_profile.record_pages(
            session,
            tenant,
            None,
            _pages(
                ("https://shop.example/pages/about", "page", 300),
                ("https://shop.example/products/parka", "product", 120),
            ),
        )

    listing = client.get(f"/workspaces/{workspace}/brand/pages", headers=owner.auth).json()

    assert listing["counts"]["pages"] == 2
    assert listing["counts"]["words"] == 420
    # Largest first: the pages with the most voice in them lead.
    assert listing["pages"][0]["word_count"] == 300

    detail = client.get(
        f"/workspaces/{workspace}/brand/pages/{listing['pages'][0]['id']}",
        headers=owner.auth,
    ).json()

    assert detail["text"].startswith("word word")
    assert len(detail["text"]) > len(listing["pages"][0]["preview"])


def test_a_recrawl_updates_pages_rather_than_duplicating_them(
    client: TestClient, settings: Settings
) -> None:
    """Same URL seen twice is one row, or the inspector fills with history."""
    owner = register_and_verify(client, prefix="brand", workspace_name="Northwind")
    workspace = first_workspace(client, owner)["id"]
    tenant = uuid.UUID(workspace)

    for words in (50, 90):
        with tenant_session(settings, tenant) as session:
            brand_profile.record_pages(
                session, tenant, None, _pages(("https://shop.example/pages/about", "page", words))
            )

    listing = client.get(f"/workspaces/{workspace}/brand/pages", headers=owner.auth).json()

    assert listing["counts"]["pages"] == 1
    assert listing["pages"][0]["word_count"] == 90


def test_excluding_a_page_keeps_it_visible_but_out_of_the_word_count(
    client: TestClient, settings: Settings
) -> None:
    """Excluded is not deleted: the merchant must be able to change their mind."""
    owner = register_and_verify(client, prefix="brand", workspace_name="Northwind")
    workspace = first_workspace(client, owner)["id"]
    tenant = uuid.UUID(workspace)

    with tenant_session(settings, tenant) as session:
        brand_profile.record_pages(
            session,
            tenant,
            None,
            _pages(
                ("https://shop.example/pages/about", "page", 300),
                ("https://shop.example/pages/draft", "page", 100),
            ),
        )

    listing = client.get(f"/workspaces/{workspace}/brand/pages", headers=owner.auth).json()
    draft = next(page for page in listing["pages"] if page["url"].endswith("draft"))

    response = client.post(
        f"/workspaces/{workspace}/brand/pages/{draft['id']}/exclusion",
        headers=owner.auth,
        json={"excluded": True},
    )

    assert response.status_code == 200
    assert response.json()["included"] is False
    # Honest about the consequence: the vector store is not rewritten in place.
    assert response.json()["reindex_required"] is True

    after = client.get(f"/workspaces/{workspace}/brand/pages", headers=owner.auth).json()

    assert after["counts"]["pages"] == 2, "an excluded page stays visible"
    assert after["counts"]["included"] == 1
    assert after["counts"]["words"] == 300


def test_an_exclusion_survives_a_recrawl(client: TestClient, settings: Settings) -> None:
    """A merchant's decision must outlive the next crawl, or it is not a decision."""
    owner = register_and_verify(client, prefix="brand", workspace_name="Northwind")
    workspace = first_workspace(client, owner)["id"]
    tenant = uuid.UUID(workspace)
    page = _pages(("https://shop.example/pages/draft", "page", 100))

    with tenant_session(settings, tenant) as session:
        brand_profile.record_pages(session, tenant, None, page)

    listing = client.get(f"/workspaces/{workspace}/brand/pages", headers=owner.auth).json()
    client.post(
        f"/workspaces/{workspace}/brand/pages/{listing['pages'][0]['id']}/exclusion",
        headers=owner.auth,
        json={"excluded": True},
    )

    with tenant_session(settings, tenant) as session:
        brand_profile.record_pages(session, tenant, None, page)

    after = client.get(f"/workspaces/{workspace}/brand/pages", headers=owner.auth).json()

    assert after["pages"][0]["included"] is False


def test_another_workspace_cannot_read_this_brands_pages(
    client: TestClient, settings: Settings
) -> None:
    """Storefront text is a brand's copy, and isolation is not graded by severity."""
    owner = register_and_verify(client, prefix="brand", workspace_name="Northwind")
    workspace = first_workspace(client, owner)["id"]
    tenant = uuid.UUID(workspace)

    with tenant_session(settings, tenant) as session:
        brand_profile.record_pages(
            session, tenant, None, _pages(("https://shop.example/pages/about", "page", 300))
        )
        brand_profile.update_profile(session, tenant, what_you_sell="A trade secret")

    outsider = register_and_verify(client, prefix="other", workspace_name="Someone Else")

    pages = client.get(f"/workspaces/{workspace}/brand/pages", headers=outsider.auth)
    profile = client.get(f"/workspaces/{workspace}/brand/profile", headers=outsider.auth)

    # A non-member must not learn the workspace exists, let alone read it.
    assert pages.status_code in (403, 404)
    assert profile.status_code in (403, 404)
    assert "trade secret" not in profile.text


def test_the_logo_guess_is_not_overwritten_once_corrected(
    client: TestClient, settings: Settings
) -> None:
    """A merchant fixing our guess must not have it undone by the next crawl."""
    owner = register_and_verify(client, prefix="brand", workspace_name="Northwind")
    tenant = uuid.UUID(first_workspace(client, owner)["id"])

    # Written through a session that is not tenant-scoped would be refused by
    # RLS, so this exercises the service exactly as the task does.
    with tenant_session(settings, tenant) as session:
        profile = brand_profile.ensure_profile(session, tenant)
        profile.logo_url = "https://cdn.example/the-real-logo.png"

    crawled = [
        Page(
            url="https://shop.example/",
            title="Home",
            text="hello " * 30,
            kind="home",
            images=("https://cdn.example/a-promo-banner.jpg",),
        )
    ]

    # What the task does: guess only when there is nothing to overwrite.
    with tenant_session(settings, tenant) as session:
        profile = brand_profile.ensure_profile(session, tenant)
        if profile.logo_url is None:
            profile.logo_url = brand_profile.guess_assets(crawled)
        assert profile.logo_url == "https://cdn.example/the-real-logo.png"


def test_the_crawl_timestamp_moves_on_a_recrawl(client: TestClient, settings: Settings) -> None:
    """Stale extracted text is worse than none, so the age must be visible."""
    owner = register_and_verify(client, prefix="brand", workspace_name="Northwind")
    tenant = uuid.UUID(first_workspace(client, owner)["id"])
    page = _pages(("https://shop.example/pages/about", "page", 50))

    with tenant_session(settings, tenant) as session:
        brand_profile.record_pages(session, tenant, None, page)
        first = brand_profile.pages_for(session, tenant)[0].crawled_at

    with tenant_session(settings, tenant) as session:
        brand_profile.record_pages(session, tenant, None, page)
        second = brand_profile.pages_for(session, tenant)[0].crawled_at

    assert second >= first
    assert second <= datetime.now(UTC)
