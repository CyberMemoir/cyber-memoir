from starlette.exceptions import HTTPException


class BodyLimitMiddleware:
    """Bound streamed/chunked request bodies, not only Content-Length headers."""

    def __init__(self, app, max_bytes):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        size = 0

        async def bounded_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > self.max_bytes:
                    raise HTTPException(413, "请求体超过大小限制")
            return message

        await self.app(scope, bounded_receive, send)
