import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .settings import settings


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.window_seconds = settings.rate_limit_window_seconds
        self.max_requests = settings.rate_limit_max_requests
        self.max_body_bytes = settings.max_request_body_bytes
        self._hits = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        # Keep health endpoint unrestricted for uptime checks.
        if request.url.path == "/health":
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_body_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large"},
                    )
            except ValueError:
                pass

        client_host = request.client.host if request.client else "unknown"
        key = f"{client_host}:{request.url.path}"
        now = time.time()
        window_start = now - self.window_seconds

        queue = self._hits[key]
        while queue and queue[0] < window_start:
            queue.popleft()

        if len(queue) >= self.max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(self.window_seconds)},
            )

        queue.append(now)
        return await call_next(request)
