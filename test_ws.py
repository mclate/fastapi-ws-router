import pytest
import starlette.websockets
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as client:
        yield client


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
def test_app(client: TestClient, model: str, body: dict):
    with client.websocket_connect("/ws2") as websocket:
        websocket.send_json(body)
        data = websocket.receive_json()
        assert data["model"] == model


def test_on_connect(client: TestClient):
    with pytest.raises(starlette.websockets.WebSocketDisconnect):
        with client.websocket_connect("/ws2", subprotocols=["Fail"]):
            pass


def test_fallback(client: TestClient):
    with client.websocket_connect("/ws2") as websocket:
        websocket.send_json({"message_type": "invalid"})
        data = websocket.receive_text()
        assert data == "Invalid message type"
