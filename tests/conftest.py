from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from typing import Callable, Dict, List, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from fastapi_ws_router import WSRouter


@pytest.fixture
def app() -> FastAPI:
    return FastAPI()


@pytest.fixture
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as client:
        yield client


WebSocketFixture = Callable[..., AbstractContextManager[WebSocketTestSession]]


@pytest.fixture
def ws(request, client: TestClient) -> WebSocketFixture:
    @contextmanager
    def inner(
        path: str = "/ws",
        subprotocols: Optional[List[str]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Generator[WebSocketTestSession, None, None]:
        conn = client.websocket_connect(
            path,
            subprotocols=subprotocols,
            headers=(headers or {}),
        )
        with conn as websocket:
            yield websocket

    return inner


@pytest.fixture
def router(app: FastAPI) -> WSRouter:
    router = WSRouter()
    app.include_router(router, prefix="/ws")
    return router
