from __future__ import annotations

import asyncio
import logging

import aiohttp

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class NotFoundError(Exception):
    pass


class FetchError(Exception):
    pass


async def fetch_json(session, url: str, retries: int, backoff_base: float) -> dict:
    attempt = 0
    while True:
        try:
            async with session.get(url) as response:
                if response.status == 404:
                    raise NotFoundError(url)
                if response.status in _RETRYABLE_STATUSES:
                    raise FetchError(f"status={response.status}")
                return await response.json()
        except NotFoundError:
            raise
        except (FetchError, aiohttp.ClientError, asyncio.TimeoutError) as exc:
            attempt += 1
            if attempt > retries:
                raise FetchError(f"{url} failed after {retries} retries: {exc}") from exc
            delay = backoff_base * (2 ** (attempt - 1))
            logger.warning("retry %d/%d for %s in %.1fs: %s", attempt, retries, url, delay, exc)
            await asyncio.sleep(delay)
