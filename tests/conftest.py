from contextlib import contextmanager
from typing import Callable, ContextManager, List, Dict, Generator, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocket

from fastapi_ws_router import WSRouter


@pytest.fixture(scope="function")
def app() -> FastAPI:
    return FastAPI()


@pytest.fixture(scope="function")
def client(app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(app) as client:
        yield client


WebSocketFixture = Callable[..., ContextManager[WebSocketTestSession]]


@pytest.fixture(scope="function")
def ws(request, client: TestClient) -> Generator[WebSocketFixture, None, None]:
    @contextmanager
    def inner(
        path: str = "/ws",
        subprotocols: Optional[List[str]] = None,
        headers: Optional[Dict[str, str]] = None,
    )-> Generator[WebSocketTestSession, None, None]:
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
