from types import GenericAlias
from typing import (
    Literal,
    Callable,
    Dict,
    Union,
    Annotated,
    Optional,
    Sequence,
    Tuple,
)

from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.routing import APIRoute, get_websocket_app
from pydantic import BaseModel, TypeAdapter, Field, ValidationError
from starlette._exception_handler import wrap_app_handling_exceptions
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import websocket_session, WebSocketRoute, Match
from starlette.types import Scope, Receive, Send
from starlette.websockets import WebSocket

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.websocket("/ws")
async def websocket(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"msg": "Hello WebSocket"})
    await websocket.close()


# class WSRoute(WebSocketRoute):
class WSRoute(APIRoute):
    _adapter: TypeAdapter

    def __init__(
        self,
        path: str,
        discriminator: str,
        name: Optional[str] = None,
        dependencies: Sequence[Depends] | None = None,
        include_in_schema: bool = True,
        dependency_overrides_provider: Optional[Callable] = None,
    ):
        super().__init__(
            path,
            self,
            methods=["POST"],
            name=name,
            dependencies=dependencies,
            dependency_overrides_provider=dependency_overrides_provider,
            include_in_schema=include_in_schema,
        )
        self.discriminator = discriminator
        self.mapping: Dict[type, Callable] = {}
        self._adapter = None
        self.app = websocket_session(
            get_websocket_app(
                dependant=self.dependant,
                dependency_overrides_provider=dependency_overrides_provider,
                embed_body_fields=self._embed_body_fields,
            )
        )
        # self.__call__ = self.__call__internal__

    def matches(self, scope: Scope) -> Tuple[Match, Scope]:
        return WebSocketRoute.matches(self, scope)

    # def url_path_for(self, name: str, /, **path_params: Any) -> URLPath:
    #     return WebSocketRoute.url_path_for(self, name, **path_params)

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        session = WebSocket(scope, receive=receive, send=send)

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            await self.__call(session)

        await wrap_app_handling_exceptions(app, session)(scope, receive, send)

    # This is how we fake the endpoint signature for the api documentation.
    # The actual communication is being handled in the `handle` method.
    async def __call__(self): ...

    async def _on_connect(self, websocket: WebSocket) -> None:
        """Override to handle an incoming websocket connection"""
        await websocket.accept()

    # async def on_receive(self, websocket: WebSocket, data: typing.Any) -> None:
    #     """Override to handle an incoming websocket message"""
    #
    # async def on_disconnect(self, websocket: WebSocket, close_code: int) -> None:
    #     """Override to handle a disconnecting websocket"""

    def _build_adapter(self) -> TypeAdapter:
        models = GenericAlias(Union, tuple(self.mapping.keys()))
        AnnotatedModels = Annotated[models, Field(discriminator=self.discriminator)]
        return TypeAdapter(AnnotatedModels)

    async def __call(self, websocket: WebSocket):
        if not self._adapter:
            self._adapter = self._build_adapter()

        await self._on_connect(websocket)

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
    message_type: Literal["user"]
    user_id: int
    user_name: str


class PostMessage(BaseModel):
    message_type: Literal["post"]
    post_id: int
    post_content: str


async def headerauth(x_token: Optional[str] = Header(None)):
    if x_token == "fail":
        raise HTTPException(status_code=400, detail="X-Token header invalid")


router = WSRoute(
    "/ws2",
    discriminator="message_type",
    dependencies=[Depends(headerauth)],
)
app.routes.append(router)


async def app2(req: Request) -> Response: ...


app.add_api_route("/static", app2, methods=["POST"], name="static")


@router.on_connect
async def on_connect(websocket: WebSocket):
    if "Fail" in websocket.scope["subprotocols"]:
        await websocket.close()
    else:
        await websocket.accept()


@router.fallback
async def fallback(websocket: WebSocket, message: str, error: ValidationError):
    await websocket.send_text("Invalid message type")


@router.receive(UserMessage)
async def get_user_message(message: UserMessage, websocket: WebSocket):
    await websocket.send_json({"model": "UserMessage"})


@router.receive(PostMessage)
async def get_post_message(message: PostMessage, websocket: WebSocket):
    await websocket.send_json({"model": "PostMessage"})
