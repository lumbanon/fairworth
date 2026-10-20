"""Bound request bytes before JSON parsing, including chunked bodies."""
from starlette.responses import JSONResponse
import asyncio


class ResearchBodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or "/ai/" not in scope.get("path", "") or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        body = bytearray()
        try:
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    chunk = message.get("body", b"")
                    if len(body) + len(chunk) > 32768:
                        return await JSONResponse({"error": {"code": "ai_request_too_large", "message": "Research requests must fit the permitted size."}}, status_code=413)(scope, receive, send)
                    body.extend(chunk)
                    if not message.get("more_body"):
                        break
        except TimeoutError:
            return await JSONResponse({"error": {"code": "ai_request_timeout", "message": "Research request upload timed out."}}, status_code=408)(scope, receive, send)
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        await self.app(scope, bounded_receive, send)
