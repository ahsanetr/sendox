"""Probe URL regression tests.

Chroma's v1 API was removed in 1.x and started returning 410 Gone, which the
readiness probe reported as a dead dependency. These tests pin the exact paths
each HTTP probe requests, so a silent API-version drift fails here instead of in
a health report nobody reads.
"""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from sendox_api.config import Settings
from sendox_api.health import run_readiness_probes

REQUESTED_PATHS: list[str] = []


class _RecordingHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # name is fixed by BaseHTTPRequestHandler
        REQUESTED_PATHS.append(self.path)
        body = b'{"nanosecond heartbeat":1}'
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        """Silence the default stderr access log."""


@pytest.fixture
def recording_server() -> Iterator[str]:
    REQUESTED_PATHS.clear()
    server = HTTPServer(("127.0.0.1", 0), _RecordingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


async def test_http_probes_request_the_expected_paths(recording_server: str) -> None:
    settings = Settings(
        env="test",
        log_level="WARNING",
        # Dead ports: only the two HTTP probes should reach the recording server.
        database_url="postgresql+psycopg://nobody:nobody@127.0.0.1:1/none",
        redis_url="redis://127.0.0.1:1/0",
        chroma_url=recording_server,
        mjml_url=recording_server,
    )

    results = {result.name: result for result in await run_readiness_probes(settings)}

    assert results["chromadb"].status == "ok"
    assert results["mjml"].status == "ok"
    # Chroma v1 is gone; requesting it would yield 410 and a false "error".
    assert sorted(REQUESTED_PATHS) == ["/api/v2/heartbeat", "/health"]


async def test_trailing_slash_in_chroma_url_does_not_double_up(recording_server: str) -> None:
    settings = Settings(
        env="test",
        log_level="WARNING",
        database_url="postgresql+psycopg://nobody:nobody@127.0.0.1:1/none",
        redis_url="redis://127.0.0.1:1/0",
        chroma_url=recording_server + "/",
        mjml_url=recording_server,
    )

    await run_readiness_probes(settings)

    assert "/api/v2/heartbeat" in REQUESTED_PATHS
    assert "//api/v2/heartbeat" not in REQUESTED_PATHS
