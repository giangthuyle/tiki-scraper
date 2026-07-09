from types import SimpleNamespace

import aiohttp
import pytest

from tiki_scraper.client import BlockedError, FetchError, NotFoundError, fetch_json


class _FakeResponse:
    def __init__(self, status: int, payload=None, content_type_error: bool = False):
        self.status = status
        self._payload = payload
        self._content_type_error = content_type_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        if self._content_type_error:
            request_info = SimpleNamespace(real_url="http://x/1")
            raise aiohttp.ContentTypeError(request_info=request_info, history=())
        return self._payload


class _FakeSession:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = 0

    def get(self, url):
        self.calls += 1
        return next(self._responses)


async def test_fetch_json_success_first_try():
    session = _FakeSession([_FakeResponse(200, {"id": 1})])
    result = await fetch_json(session, "http://x/1", retries=3, backoff_base=0.0)
    assert result == {"id": 1}
    assert session.calls == 1


async def test_fetch_json_404_raises_without_retry():
    session = _FakeSession([_FakeResponse(404)])
    with pytest.raises(NotFoundError):
        await fetch_json(session, "http://x/1", retries=3, backoff_base=0.0)
    assert session.calls == 1


async def test_fetch_json_retries_on_5xx_then_succeeds():
    session = _FakeSession([_FakeResponse(500), _FakeResponse(200, {"id": 1})])
    result = await fetch_json(session, "http://x/1", retries=3, backoff_base=0.0)
    assert result == {"id": 1}
    assert session.calls == 2


async def test_fetch_json_raises_fetch_error_after_exhausting_retries():
    session = _FakeSession([_FakeResponse(500), _FakeResponse(500), _FakeResponse(500)])
    with pytest.raises(FetchError):
        await fetch_json(session, "http://x/1", retries=2, backoff_base=0.0)
    assert session.calls == 3


async def test_fetch_json_raises_blocked_error_on_repeated_non_json_200():
    session = _FakeSession(
        [
            _FakeResponse(200, content_type_error=True),
            _FakeResponse(200, content_type_error=True),
            _FakeResponse(200, content_type_error=True),
        ]
    )
    with pytest.raises(BlockedError):
        await fetch_json(session, "http://x/1", retries=2, backoff_base=0.0)
    assert session.calls == 3


async def test_fetch_json_blocked_error_is_a_fetch_error():
    assert issubclass(BlockedError, FetchError)
