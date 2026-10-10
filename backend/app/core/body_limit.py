"""
Refuse a request body that is too large while it is still arriving.

FastAPI reads a whole multipart upload before the endpoint runs, so a size check inside the endpoint
only happens after the memory and disk have already been spent. This middleware counts the bytes as
they come in and answers 413 as soon as the limit is passed, whether or not the client announced a
Content-Length.

It answers itself and then tells the application the client has gone: raising an exception from the
body reader is not an option, because FastAPI turns every exception raised while it parses a body into
a generic 400.
"""
from typing import Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# The multipart envelope (boundaries, the token field, headers) around the recording itself.
ENVELOPE_ALLOWANCE_BYTES = 64 * 1024


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, limit: Callable[[], int]) -> None:
        self.app = app
        self.limit = limit  # read per request, so a changed setting applies at once

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return

        maximum = self.limit() + ENVELOPE_ALLOWANCE_BYTES
        announced = dict(scope["headers"]).get(b"content-length")
        if announced is not None and announced.isdigit() and int(announced) > maximum:
            await self._refuse(scope, receive, send, maximum)
            return

        received = 0
        refused = False

        async def counting_receive() -> Message:
            nonlocal received, refused
            if refused:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > maximum:
                    refused = True
                    await self._refuse(scope, receive, send, maximum)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            if not refused:  # once 413 has been sent, whatever the application says next is dropped
                await send(message)

        await self.app(scope, counting_receive, guarded_send)

    @staticmethod
    async def _refuse(scope: Scope, receive: Receive, send: Send, maximum: int) -> None:
        response = JSONResponse(
            {"detail": f"The request is larger than the {maximum // (1024 * 1024)} MB limit."},
            status_code=413,
            headers={"Connection": "close"},
        )
        await response(scope, receive, send)
