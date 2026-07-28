"""Receive-level caps for confidential multipart evidence uploads.

FastAPI resolves ``UploadFile`` parameters before calling the endpoint.  This
pure ASGI middleware therefore counts bytes before Starlette can spool a large
multipart body to its temporary storage.
"""

from __future__ import annotations

from typing import Any

from starlette.responses import JSONResponse

MULTIPART_ENVELOPE_BYTES = 256 * 1024


class EvidenceUploadLimitMiddleware:
    def __init__(
        self,
        app: Any,
        *,
        api_prefix: str,
        file_limit: int,
        staff_screening_file_limit: int | None = None,
    ) -> None:
        self.app = app
        self.api_prefix = api_prefix.rstrip("/")
        self.family_body_limit = file_limit + MULTIPART_ENVELOPE_BYTES
        self.staff_screening_body_limit = (
            staff_screening_file_limit + MULTIPART_ENVELOPE_BYTES
            if staff_screening_file_limit is not None
            else self.family_body_limit
        )

    def _body_limit(self, scope: dict[str, Any]) -> int | None:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            return None
        path = str(scope.get("path", ""))
        prefix = f"{self.api_prefix}/families/"
        if path.startswith(prefix):
            remainder = path[len(prefix) :].split("/")
            if len(remainder) == 3 and remainder[1:] == [
                "authority",
                "evidence-objects",
            ]:
                return self.family_body_limit
        screening = f"{self.api_prefix}/marketplace/screening-documents"
        if path == screening:
            return self.staff_screening_body_limit
        screening_remainder = path.removeprefix(f"{screening}/").split("/")
        if (
            path.startswith(f"{screening}/")
            and len(screening_remainder) == 2
            and screening_remainder[1] == "versions"
        ):
            return self.staff_screening_body_limit
        transport_self = f"{self.api_prefix}/staff/self/transport-registry"
        if path == f"{transport_self}/qualification-evidence" or (
            path.startswith(f"{transport_self}/vehicles/") and path.endswith("/evidence")
        ):
            return self.staff_screening_body_limit
        transport_manager = f"{self.api_prefix}/staff/transport-registry/vehicles/"
        if path.startswith(transport_manager) and path.endswith("/evidence"):
            return self.staff_screening_body_limit
        return None

    @staticmethod
    def _content_length(scope: dict[str, Any]) -> int | None:
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    parsed = int(value)
                except ValueError:
                    return -1
                return parsed if parsed >= 0 else -1
        return None

    async def _reject(self, scope, receive, send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": {"code": "evidence_upload_body_too_large"}},
        )
        await response(scope, receive, send)

    async def __call__(self, scope, receive, send) -> None:
        body_limit = self._body_limit(scope)
        if body_limit is None:
            await self.app(scope, receive, send)
            return
        content_length = self._content_length(scope)
        if content_length == -1 or (
            content_length is not None and content_length > body_limit
        ):
            await self._reject(scope, receive, send)
            return

        received = 0
        overflowed = False
        buffered_response: list[dict[str, Any]] = []

        async def capped_receive() -> dict[str, Any]:
            nonlocal received, overflowed
            if overflowed:
                return {"type": "http.disconnect"}
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > body_limit:
                    overflowed = True
                    return {"type": "http.disconnect"}
            return message

        async def buffered_send(message: dict[str, Any]) -> None:
            buffered_response.append(message)

        await self.app(scope, capped_receive, buffered_send)
        if overflowed:
            await self._reject(scope, receive, send)
            return
        for message in buffered_response:
            await send(message)
