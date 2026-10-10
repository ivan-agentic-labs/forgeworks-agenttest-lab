"""Bound actual received bytes before JSON deserialization, including chunked input."""
from starlette.responses import JSONResponse

MAX_REQUEST_BYTES = 8 * 1024 * 1024


class BodyBudgetMiddleware:
    def __init__(self, app, max_bytes=MAX_REQUEST_BYTES):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect": return
            body = message.get("body", b"")
            size += len(body)
            if size > self.max_bytes:
                response = JSONResponse({"type": "about:blank", "title": "Request rejected", "status": 413, "code": "REQUEST_BODY_TOO_LARGE", "detail": "Request exceeds the 8 MiB body budget", "request_id": "runtime"}, status_code=413)
                return await response(scope, receive, send)
            if body: chunks.append(body)
            if not message.get("more_body", False): break
        content = b"".join(chunks)
        del chunks
        consumed = False
        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": content, "more_body": False}
            return await receive()
        await self.app(scope, replay, send)
