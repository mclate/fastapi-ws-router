from functools import partial
from types import GenericAlias
from typing import Literal, Callable, Dict, Union, Annotated

from fastapi import FastAPI
from pydantic import BaseModel, TypeAdapter, Field, ValidationError
from starlette._exception_handler import wrap_app_handling_exceptions
from starlette.routing import websocket_session
from starlette.types import Scope, Receive, Send
from starlette.websockets import WebSocket

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.websocket("/ws")
async def websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"msg": "Hello WebSocket"})
    await websocket.close()


class WSRouter:
    _on_connect: Callable
    _adapter: TypeAdapter

    def __init__(self, discriminator: str):
        self.discriminator = discriminator
        self.mapping: Dict[type, Callable] = {}
        self._on_connect = None
        self._adapter = None
        self.__call__ = websocket_session(partial(self.__call, self=self))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        session = WebSocket(scope, receive=receive, send=send)

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            await self.__call(session)

        await wrap_app_handling_exceptions(app, session)(scope, receive, send)

    def _build_adapter(self) -> TypeAdapter:
        models = GenericAlias(Union, tuple(self.mapping.keys()))
        AnnotatedModels = Annotated[models, Field(discriminator=self.discriminator)]
        return TypeAdapter(AnnotatedModels)

    async def __call(self, websocket: WebSocket):
        if not self._adapter:
            self._adapter = self._build_adapter()

        if self._on_connect:
            await self._on_connect(websocket)
        await websocket.accept()

        message = await websocket.receive_text()
        try:
            validated = self._adapter.validate_json(message)
        except ValidationError as e:
            await self._fallback(websocket, message, e)
            return

        handler = self.mapping[validated.__class__]
        await handler(validated, websocket)

        # await websocket.send_json({"msg": "Hello WebSocket"})
        await websocket.close()

    def on_connect(self, func):
        self._on_connect = func
        return func

    def receive(self, model: type):
        def decorator(func):
            self.mapping[model] = func
            return func

        return decorator

    def fallback(self, func):
        self._fallback = func
        return func


class UserMessage(BaseModel):
    message_type: Literal['user']
    user_id: int
    user_name: str


class PostMessage(BaseModel):
    message_type: Literal['post']
    post_id: int
    post_content: str


router = WSRouter(discriminator="message_type")
app.add_websocket_route("/ws2", router)


@router.on_connect
async def on_connect(websocket: WebSocket):
    if 'Fail' in websocket.scope['subprotocols']:
        await websocket.close()


@router.fallback
async def fallback(websocket: WebSocket, message: str, error: ValidationError):
    await websocket.send_text("Invalid message type")


@router.receive(UserMessage)
async def get_user_message(message: UserMessage, websocket: WebSocket):
    await websocket.send_json({"model": "UserMessage"})


@router.receive(PostMessage)
async def get_post_message(message: PostMessage, websocket: WebSocket):
    await websocket.send_json({"model": "PostMessage"})
