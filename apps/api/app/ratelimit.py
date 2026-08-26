"""Lightweight per-IP rate limiting for public, unauthenticated endpoints.

Uses an in-memory fixed window, which is enough for a single-instance
deployment. A horizontally scaled setup would need shared storage (e.g. Redis)
or rate limiting at the reverse proxy in front of the gateway.
"""

import time
from threading import Lock

from fastapi import HTTPException, Request, status

from .config import get_settings


def client_ip(request: Request) -> str:
    """Best-effort client address.

    The gateway forwards the caller in ``X-Forwarded-For``; the left-most entry
    is the originating client. It is only as trustworthy as the proxy chain, so
    treat it as a throttling hint, not an identity.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    """FastAPI dependency that allows ``times`` requests per ``seconds`` per IP."""

    def __init__(self, times: int, seconds: int, *, name: str) -> None:
        self.times = times
        self.seconds = seconds
        self.name = name
        self._hits: dict[str, tuple[int, float]] = {}
        self._lock = Lock()

    def _register(self, identifier: str) -> tuple[int, float]:
        now = time.monotonic()
        with self._lock:
            count, window_start = self._hits.get(identifier, (0, now))
            if now - window_start >= self.seconds:
                count, window_start = 0, now
            count += 1
            self._hits[identifier] = (count, window_start)
            # Bound memory: drop windows that have already expired.
            if len(self._hits) > 10_000:
                self._hits = {k: v for k, v in self._hits.items() if now - v[1] < self.seconds}
        return count, window_start

    def __call__(self, request: Request) -> None:
        if not get_settings().rate_limit_enabled:
            return
        count, window_start = self._register(f"{self.name}:{client_ip(request)}")
        if count > self.times:
            retry_after = max(1, int(self.seconds - (time.monotonic() - window_start)))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again.",
                headers={"Retry-After": str(retry_after)},
            )


# Shared limiters. Credential endpoints are strict (brute-force defense); the
# widget message endpoint is throttled because each call spends LLM tokens.
login_rate_limit = RateLimiter(10, 60, name="login")
widget_rate_limit = RateLimiter(30, 60, name="widget")
public_asset_rate_limit = RateLimiter(60, 60, name="public-asset")
# The Meta webhook is authenticated by its HMAC signature; this generous limit
# only guards against floods of unsigned traffic.
whatsapp_cloud_webhook_rate_limit = RateLimiter(300, 60, name="whatsapp-cloud-webhook")
