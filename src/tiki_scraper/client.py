from __future__ import annotations

import asyncio
import json
import logging

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class NotFoundError(Exception):
    pass


class FetchError(Exception):
    pass


class BlockedError(FetchError):
    """A 200 response whose body isn't JSON — the WAF challenge-page
    signature, distinct from an ordinary transient failure so callers can
    react to it specifically (e.g. back off concurrency)."""


class _NonJsonBody(FetchError):
    """Internal marker: the page loaded but its body didn't parse as JSON
    (WAF challenge page). Retried like any transient error; promoted to
    BlockedError once retries are exhausted."""


async def fetch_json(page, url: str, retries: int, backoff_base: float) -> dict:
    """Fetch `url` on a persistent CloakBrowser (stealth Chromium) page and
    return the parsed JSON body. The page is REUSED across requests so the
    anti-bot cookie Tiki sets after its JS WAF challenge persists — a fresh
    page per request would re-trigger the challenge every time. `networkidle`
    waits for that challenge JS to finish before we read the body."""
    attempt = 0
    while True:
        try:
            response = await page.goto(url, wait_until="networkidle")
            if response.status == 404:
                raise NotFoundError(url)
            if response.status in _RETRYABLE_STATUSES:
                raise FetchError(f"status={response.status}")
            body = await response.text()
            try:
                return json.loads(body)
            except json.JSONDecodeError as exc:  # empty/HTML body == WAF challenge page
                raise _NonJsonBody(str(exc)) from exc
        except NotFoundError:
            raise
        except Exception as exc:  # navigation errors, timeouts, protocol errors, _NonJsonBody
            attempt += 1
            if attempt > retries:
                if isinstance(exc, _NonJsonBody):
                    raise BlockedError(f"{url} blocked after {retries} retries: {exc}") from exc
                raise FetchError(f"{url} failed after {retries} retries: {exc}") from exc
            delay = backoff_base * (2 ** (attempt - 1))
            logger.warning("retry %d/%d for %s in %.1fs: %s", attempt, retries, url, delay, exc)
            await asyncio.sleep(delay)
