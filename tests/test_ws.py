from typing import Callable, Dict, Literal, Optional, Union

import pytest
from fastapi import Depends, FastAPI, Header, Path
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from starlette.websockets import WebSocket, WebSocketDisconnect

from fastapi_ws_router import WSRouter

from .conftest import WebSocketFixture


class UserMessage(BaseModel):
    message_type: Literal["user"]
    user_id: int
    user_name: str


class PostMessage(BaseModel):
    message_type: Literal["post"]
    post_id: int
    post_content: str


@pytest.mark.parametrize(
    ("model", "body"),
    [
        ("UserMessage", {"message_type": "user", "user_id": 1, "user_name": "John"}),
        (
            "PostMessage",
            {"message_type": "post", "post_id": 1, "post_content": "Hello, world!"},
        ),
    ],
)
def test_app(router: WSRouter, ws: WebSocketFixture, model: str, body: dict):
    @router.receive(UserMessage)
    async def get_user_message(websocket: WebSocket, message: UserMessage):
        await websocket.send_json({"model": "UserMessage"})

    @router.receive(PostMessage, callbacks=Union[UserMessage, PostMessage])  # type: ignore[arg-type]
    async def get_post_message(websocket: WebSocket, message: PostMessage):
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

    with pytest.raises(WebSocketDisconnect):  # noqa: SIM117
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
        assert error.args[0] == 'WebSocket is not connected. Need to call "accept" first.'
        await websocket.close()
        closed = True

    with pytest.raises(WebSocketDisconnect):  # noqa: SIM117
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


def test_empty_mapping(router: WSRouter, ws: WebSocketFixture):
    with ws() as websocket:
        websocket.send_text("")


def test_empty_mapping_fallback(router: WSRouter, ws: WebSocketFixture):
    called = False

    @router.fallback
    async def fallback(websocket: WebSocket, message, error):  # noqa: RUF029
        nonlocal called
        called = True
        assert message == "empty"

    with ws() as websocket:
        websocket.send_text("empty")
    assert called


def test_fail_header(app: FastAPI, ws: WebSocketFixture):
    async def headerauth(x_token: Optional[str] = Header(None)):  # noqa: RUF029
        if x_token == "fail":
            raise WebSocketDisconnect(123, "Fail header")

    router = WSRouter(dependencies=[Depends(headerauth)])
    app.include_router(router, prefix="/ws")

    with pytest.raises(WebSocketDisconnect) as err:  # noqa: SIM117
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
    async def path(websocket: WebSocket, item: str = Path(...)):  # noqa: RUF029
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
    async def on_disconnect(websocket: WebSocket, code: int, reason: str):  # noqa: RUF029
        nonlocal disconnected
        disconnected = True
        assert code == 1000

    with ws() as websocket:
        websocket.close()

    assert disconnected


def test_custom_dispatcher(app: FastAPI, ws: WebSocketFixture):
    called = False

    class Message(BaseModel): ...

    async def handler(message: Message, websocket: WebSocket):  # noqa: RUF029
        pytest.fail("Unexpected use of default dispatcher")  # Will not be called because dispatcher didn't dispatch

    async def dispatcher(websocket: WebSocket, mapping: Dict[type, Callable[..., None]], message: Union[str, bytes]):  # noqa: RUF029
        nonlocal called
        assert mapping == {Message: handler}
        assert message == '{"a":"1234"}'
        called = True

    router = WSRouter(dispatcher=dispatcher)
    router.receive(Message)(handler)
    app.include_router(router, prefix="/ws")

    with ws() as websocket:
        websocket.send_json({"a": "1234"})

    assert called


def test_multiple_messages(router: WSRouter, ws: WebSocketFixture):
    messages = 0

    @router.receive(UserMessage)
    async def handler1(websocket: WebSocket, message: UserMessage):  # noqa: RUF029
        nonlocal messages
        messages += 1

    with ws() as websocket:
        websocket.send_json({"message_type": "user", "user_id": 1, "user_name": "John"})
        websocket.send_json({"message_type": "user", "user_id": 1, "user_name": "John"})
        websocket.send_json({"message_type": "user", "user_id": 1, "user_name": "John"})
    assert messages == 3
