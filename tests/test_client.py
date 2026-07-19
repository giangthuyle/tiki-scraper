import pytest

from tiki_scraper.client import BlockedError, FetchError, NotFoundError, fetch_json


class _FakeResponse:
    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body

    async def text(self):
        return self._body


class _FakePage:
    """Stands in for a CloakBrowser page: `goto` returns queued responses."""

    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = 0
        self.last_url = None

    async def goto(self, url, wait_until=None):
        self.calls += 1
        self.last_url = url
        return next(self._responses)


async def test_fetch_json_success_first_try():
    page = _FakePage([_FakeResponse(200, '{"id": 1}')])
    assert await fetch_json(page, "http://x/1", retries=3, backoff_base=0.0) == {"id": 1}
    assert page.calls == 1


async def test_fetch_json_404_raises_without_retry():
    page = _FakePage([_FakeResponse(404, "")])
    with pytest.raises(NotFoundError):
        await fetch_json(page, "http://x/1", retries=3, backoff_base=0.0)
    assert page.calls == 1


async def test_fetch_json_retries_on_5xx_then_succeeds():
    page = _FakePage([_FakeResponse(500, ""), _FakeResponse(200, '{"id": 1}')])
    assert await fetch_json(page, "http://x/1", retries=3, backoff_base=0.0) == {"id": 1}
    assert page.calls == 2


async def test_fetch_json_raises_fetch_error_after_exhausting_retries():
    page = _FakePage([_FakeResponse(500, "")] * 3)
    with pytest.raises(FetchError):
        await fetch_json(page, "http://x/1", retries=2, backoff_base=0.0)
    assert page.calls == 3


async def test_fetch_json_raises_blocked_error_on_repeated_non_json_200():
    page = _FakePage([_FakeResponse(200, "<html>challenge</html>")] * 3)
    with pytest.raises(BlockedError):
        await fetch_json(page, "http://x/1", retries=2, backoff_base=0.0)
    assert page.calls == 3


async def test_fetch_json_retries_navigation_errors():
    class _FlakyPage(_FakePage):
        async def goto(self, url, wait_until=None):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("navigation timeout")
            return _FakeResponse(200, '{"id": 1}')

    page = _FlakyPage([])
    assert await fetch_json(page, "http://x/1", retries=3, backoff_base=0.0) == {"id": 1}
    assert page.calls == 2


async def test_fetch_json_blocked_error_is_a_fetch_error():
    assert issubclass(BlockedError, FetchError)
