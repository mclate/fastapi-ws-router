from contextlib import contextmanager
from typing import Callable, ContextManager, List, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocket

from fastapi_ws_router import WSRouter


@pytest.fixture(scope="function")
def app() -> FastAPI:
    return FastAPI()


@pytest.fixture(scope="function")
def client(app: FastAPI) -> TestClient:
    with TestClient(app) as client:
        yield client


WebSocketFixture = Callable[..., ContextManager[WebSocket]]


@pytest.fixture(scope="function")
def ws(request, client: TestClient) -> WebSocketFixture:
    @contextmanager
    def inner(
        path: str = "/ws",
        subprotocols: List[str] = None,
        headers: Dict[str, str] = None,
    ):
        conn = client.websocket_connect(
            path,
            subprotocols=subprotocols,
            headers=(headers or {}),
        )
        with conn as websocket:
            yield websocket

    yield inner


@pytest.fixture(scope="function")
def router(app: FastAPI) -> WSRouter:
    router = WSRouter()
    app.include_router(router, prefix="/ws")
    return router
