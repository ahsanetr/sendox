"""Crawl the fixture storefront into the newest workspace. Development only.

Exists so the brand inspector can be seen, screenshotted and reviewed without a
connected Shopify store, which is the thing currently blocking every other way
of filling it. It reuses the same fixture the crawler tests use, so the text on
screen can be checked against a source file rather than taken on trust.

Run from apps/api:  uv run python scripts/seed-brand-fixture.py
"""

import asyncio
import socketserver
import sys
import threading

sys.path.insert(0, "src")
sys.path.insert(0, ".")
from sqlalchemy import select
from tests.test_storefront_fixture import _Handler  # reuse the Shopify-shaped routes

from sendox_api.clients.storefront import StorefrontCrawler
from sendox_api.config import get_settings
from sendox_api.db import global_session, tenant_session
from sendox_api.models import Tenant
from sendox_api.services import brand_profile

settings = get_settings()
with global_session(settings) as s:
    tenant = s.scalars(select(Tenant).order_by(Tenant.created_at.desc())).first()
    tid, tname = tenant.id, tenant.name
print(f"seeding into workspace {tname} ({tid})")

with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as server:
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    report = asyncio.run(StorefrontCrawler(origin, delay=0).crawl())
    server.shutdown()

print(
    f"crawled {len(report.pages)} pages, {report.words} words, "
    f"{sum(len(p.images) for p in report.pages)} images"
)
with tenant_session(settings, tid) as session:
    brand_profile.record_pages(session, tid, None, report.pages)
    profile = brand_profile.ensure_profile(session, tid)
    if profile.logo_url is None:
        profile.logo_url = brand_profile.guess_assets(report.pages)
    print("logo guess:", profile.logo_url)
print("done")
