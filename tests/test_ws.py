from typing import Literal, Union, Optional

import pytest
from fastapi import FastAPI, Depends, Header, Path
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from starlette.websockets import WebSocket, WebSocketDisconnect

from conftest import WebSocketFixture
from fastapi_ws_router import WSRouter


class UserMessage(BaseModel):
    message_type: Literal["user"]
    user_id: int
    user_name: str


class PostMessage(BaseModel):
    message_type: Literal["post"]
    post_id: int
    post_content: str


@pytest.mark.parametrize(
    "model, body",
    (
        ("UserMessage", {"message_type": "user", "user_id": 1, "user_name": "John"}),
        (
            "PostMessage",
            {"message_type": "post", "post_id": 1, "post_content": "Hello, world!"},
        ),
    ),
)
def test_app(router: WSRouter, ws: WebSocketFixture, model: str, body: dict):
    @router.receive(UserMessage)
    async def get_user_message(message: UserMessage, websocket: WebSocket):
        await websocket.send_json({"model": "UserMessage"})

    @router.receive(PostMessage, callbacks=Union[UserMessage, PostMessage])
    async def get_post_message(message: PostMessage, websocket: WebSocket):
        await websocket.send_json({"model": "PostMessage"})

    with ws() as client:
        client.send_json(body)
        data = client.receive_json()
        assert data["model"] == model, data


def test_on_connect(router: WSRouter, ws: WebSocketFixture):
    @router.on_connect
    async def on_connect(websocket: WebSocket):
        if "Fail" in websocket.scope["subprotocols"]:
            await websocket.close()
        else:
            await websocket.accept()

    with pytest.raises(WebSocketDisconnect):
        with ws(subprotocols=["Fail"]):
            pass


def test_on_connect_error(router: WSRouter, ws: WebSocketFixture):
    @router.on_connect
    async def on_connect(websocket: WebSocket):
        # Forgot to call websocket.accept() or websocket.close()
        ...

    closed = False

    @router.fallback
    async def fallback(websocket: WebSocket, message: str, error: RuntimeError):
        nonlocal closed
        assert (
            error.args[0] == 'WebSocket is not connected. Need to call "accept" first.'
        )
        await websocket.close()
        closed = True

    with pytest.raises(WebSocketDisconnect):
        with ws(subprotocols=["Fail"]):
            pass

    assert closed


def test_fallback(router: WSRouter, ws: WebSocketFixture):
    @router.fallback
    async def fallback(websocket: WebSocket, message: str, error: ValidationError):
        await websocket.send_text("Invalid message type")

    with ws() as websocket:
        websocket.send_json({"message_type": "invalid"})
        data = websocket.receive_text()
        assert data == "Invalid message type"


def test_fallback_bytes(router: WSRouter, ws: WebSocketFixture):
    @router.on_bytes
    async def fallback_bytes(websocket: WebSocket):
        await websocket.send_text("Bytes fallback")

    with ws() as websocket:
        websocket.send_bytes(b"something")
        data = websocket.receive_text()
        assert data == "Bytes fallback"


def test_empty_mapping(router: WSRouter, ws: WebSocketFixture):
    with ws() as websocket:
        websocket.send_text("")


def test_empty_mapping_fallback(router: WSRouter, ws: WebSocketFixture):
    called = False

    @router.fallback
    async def fallback(websocket: WebSocket, message, error):
        nonlocal called
        called = True
        assert message == "empty"

    with ws() as websocket:
        websocket.send_text("empty")
    assert called


def test_fail_header(app: FastAPI, ws: WebSocketFixture):
    async def headerauth(x_token: Optional[str] = Header(None)):
        if x_token == "fail":
            raise WebSocketDisconnect(123, "Fail header")

    router = WSRouter(dependencies=[Depends(headerauth)])
    app.include_router(router, prefix="/ws")

    with pytest.raises(WebSocketDisconnect) as err:
        with ws(headers={"X-Token": "fail"}) as websocket:
            websocket.send_text("")
    assert err.value.code == 123
    assert err.value.reason == "Fail header"

    # This should not fail
    with ws(headers={"X-Token": "dont_fail"}) as websocket:
        websocket.send_text("")


def test_incorrect_route(router: WSRouter, client: TestClient):
    @router.receive(UserMessage)
    async def get_user_message(message: UserMessage, websocket: WebSocket):
        await websocket.send_json({"model": "UserMessage"})

    # There is such route in the list of routes. We have to make sure that we're unable to match it.
    res = client.post("/ws2 (get_user_message)")
    assert res.status_code == 404


def test_path_params(app: FastAPI, ws: WebSocketFixture):
    async def path(websocket: WebSocket, item: str = Path(...)):
        assert item == "test"
        websocket.scope["path_item"] = item

    router = WSRouter(dependencies=[Depends(path)])
    app.include_router(router, prefix="/ws/{item}")

    valid = False

    @router.on_connect
    async def on_connect(websocket: WebSocket):
        nonlocal valid
        assert websocket.scope["path_item"] == "test"
        await websocket.accept()
        valid = True

    with ws(path="/ws/test") as websocket:
        websocket.send_text("")

    assert valid


def test_client_disconnect(router: WSRouter, ws: WebSocketFixture):
    disconnected = False

    @router.on_disconnect
    async def on_disconnect(websocket: WebSocket, err: WebSocketDisconnect):
        nonlocal disconnected
        disconnected = True
        assert err.code == 1000

    with ws() as websocket:
        websocket.close()

    assert disconnected
