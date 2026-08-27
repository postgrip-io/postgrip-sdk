from __future__ import annotations

import json
from typing import Any


class FakeResponse:
    def __init__(self, value: object):
        self.body = value if isinstance(value, bytes) else json.dumps(value).encode()
        self.offset = 0

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int = -1) -> bytes:
        end = len(self.body) if limit < 0 else min(self.offset + limit, len(self.body))
        chunk = self.body[self.offset:end]
        self.offset = end
        return chunk


class FakeOpener:
    def __init__(self, responses: list[object]):
        self.responses = responses
        self.requests: list[Any] = []
        self.handlers: list[object] = []

    def add_handler(self, handler: object) -> None:
        self.handlers.append(handler)

    def open(self, request: object, timeout: float = 0) -> FakeResponse:
        self.requests.append(request)
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return FakeResponse(value)
