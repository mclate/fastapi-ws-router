from enum import Enum
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
    List,
    Any,
    Type,
)
from typing_extensions import Doc

from fastapi import FastAPI, Depends, Header, HTTPException, params
from fastapi.routing import APIRoute, get_websocket_app, APIRouter
from pydantic import BaseModel, TypeAdapter, Field, ValidationError
from starlette._exception_handler import wrap_app_handling_exceptions
from starlette.routing import websocket_session, WebSocketRoute, Match
from starlette.types import Scope, Receive, Send, Lifespan
from starlette.websockets import WebSocket

app = FastAPI()


class UserMessage(BaseModel):
    message_type: Literal["user"]
    user_id: int
    user_name: str


class PostMessage(BaseModel):
    message_type: Literal["post"]
    post_id: int
    post_content: str


@app.get("/", response_model=Union[UserMessage, PostMessage])
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


class WSMainRoute(APIRoute):
    _adapter: TypeAdapter

    def __init__(
        self,
        path: str,
        endpoint: Callable,
        name: Optional[str] = None,
        dependencies: Sequence[Depends] | None = None,
        include_in_schema: bool = True,
        dependency_overrides_provider: Optional[Callable] = None,
        response_model: type = None,
        tags: List[str] = None,
        **kwargs,
    ):
        super().__init__(
            path,
            endpoint=endpoint,
            name=name,
            dependencies=dependencies,
            dependency_overrides_provider=dependency_overrides_provider,
            response_model=response_model,
            include_in_schema=include_in_schema,
            tags=tags,
            **kwargs,
        )
        self.app = websocket_session(
            get_websocket_app(
                dependant=self.dependant,
                dependency_overrides_provider=dependency_overrides_provider,
                embed_body_fields=self._embed_body_fields,
            )
        )

    def matches(self, scope: Scope) -> Tuple[Match, Scope]:
        return WebSocketRoute.matches(self, scope)

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        session = WebSocket(scope, receive=receive, send=send)

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            await self.endpoint(session)

        await wrap_app_handling_exceptions(app, session)(scope, receive, send)


class WSRoute(APIRoute):
    """This is a "mocked" route that never matches. It's there only for the documentation"""

    def matches(self, scope: Scope) -> Tuple[Match, Scope]:
        return Match.NONE, {}


class WSRouter(APIRouter):
    def __init__(
        self,
        *,
        discriminator: Annotated[
            str, Doc("The field name to use as a discriminator.")
        ] = None,
        prefix: Annotated[str, Doc("An optional path prefix for the router.")] = "",
        tags: Annotated[
            Optional[List[Union[str, Enum]]],
            Doc(
                """
                A list of tags to be applied to all the *path operations* in this
                router.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).
                """
            ),
        ] = None,
        dependencies: Annotated[
            Optional[Sequence[params.Depends]],
            Doc(
                """
                A list of dependencies (using `Depends()`) to be applied to all the
                *path operations* in this router.

                Read more about it in the
                [FastAPI docs for Bigger Applications - Multiple Files](https://fastapi.tiangolo.com/tutorial/bigger-applications/#include-an-apirouter-with-a-custom-prefix-tags-responses-and-dependencies).
                """
            ),
        ] = None,
        dependency_overrides_provider: Annotated[
            Optional[Any],
            Doc(
                """
                Only used internally by FastAPI to handle dependency overrides.

                You shouldn't need to use it. It normally points to the `FastAPI` app
                object.
                """
            ),
        ] = None,
        on_startup: Annotated[
            Optional[Sequence[Callable[[], Any]]],
            Doc(
                """
                A list of startup event handler functions.

                You should instead use the `lifespan` handlers.

                Read more in the [FastAPI docs for `lifespan`](https://fastapi.tiangolo.com/advanced/events/).
                """
            ),
        ] = None,
        on_shutdown: Annotated[
            Optional[Sequence[Callable[[], Any]]],
            Doc(
                """
                A list of shutdown event handler functions.

                You should instead use the `lifespan` handlers.

                Read more in the
                [FastAPI docs for `lifespan`](https://fastapi.tiangolo.com/advanced/events/).
                """
            ),
        ] = None,
        # the generic to Lifespan[AppType] is the type of the top level application
        # which the router cannot know statically, so we use typing.Any
        lifespan: Annotated[
            Optional[Lifespan[Any]],
            Doc(
                """
                A `Lifespan` context manager handler. This replaces `startup` and
                `shutdown` functions with a single context manager.

                Read more in the
                [FastAPI docs for `lifespan`](https://fastapi.tiangolo.com/advanced/events/).
                """
            ),
        ] = None,
        deprecated: Annotated[
            Optional[bool],
            Doc(
                """
                Mark all *path operations* in this router as deprecated.

                It will be added to the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Path Operation Configuration](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/).
                """
            ),
        ] = None,
        include_in_schema: Annotated[
            bool,
            Doc(
                """
                To include (or not) all the *path operations* in this router in the
                generated OpenAPI.

                This affects the generated OpenAPI (e.g. visible at `/docs`).

                Read more about it in the
                [FastAPI docs for Query Parameters and String Validations](https://fastapi.tiangolo.com/tutorial/query-params-str-validations/#exclude-from-openapi).
                """
            ),
        ] = True,
        name: str = None,
        callbacks: Any = None,
    ) -> None:
        super().__init__(
            on_startup=on_startup,
            on_shutdown=on_shutdown,
            lifespan=lifespan,
            prefix=prefix,
            route_class=WSRoute,
            tags=tags,
            dependencies=dependencies,
            dependency_overrides_provider=dependency_overrides_provider,
            deprecated=deprecated,
            include_in_schema=include_in_schema,
        )
        self._adapter = None
        self.discriminator = discriminator
        self.mapping: Dict[type, Callable] = {}
        # self.add_api_route(
        #     path="",
        #     route_class_override=WSRoute,
        #     endpoint=WSRoute(
        #         path=self.prefix, endpoint=None, discriminator=discriminator
        #     ),
        #     methods=["POST"],
        # )
        self.routes.append(
            WSMainRoute(
                path="",
                endpoint=self.handler,
                methods=["POST"],
                name=name,
                dependencies=dependencies,
                dependency_overrides_provider=dependency_overrides_provider,
                tags=tags,
                response_model=callbacks,
            ),
            # WSRoute(endpoint=self.prefix, discriminator=discriminator),
        )

    def _build_adapter(self) -> TypeAdapter:
        models = GenericAlias(Union, tuple(self.mapping.keys()))
        AnnotatedModels = Annotated[models, Field(discriminator=self.discriminator)]
        return TypeAdapter(AnnotatedModels)

    async def handler(self, websocket: WebSocket):
        if not self._adapter:
            self._adapter = self._build_adapter()

        await self._on_connect(websocket)

        try:
            message = await websocket.receive_text()
        except KeyError:  # didn't receive text
            await self._fallback_bytes(websocket)
            return

        try:
            validated = self._adapter.validate_json(message)
        except ValidationError as e:
            await self._fallback(websocket, message, e)
            return

        handler = self.mapping[validated.__class__]
        await handler(validated, websocket)

        await websocket.close()

    async def _on_connect(self, websocket: WebSocket) -> None:
        """Override to handle an incoming websocket connection"""
        await websocket.accept()

    def on_connect(self, func):
        self._on_connect = func
        return func

    def receive(self, model: Type[BaseModel], callbacks: Union[Type[BaseModel]] = None):
        def decorator(func):
            self.mapping[model] = func
            self.routes.append(
                WSRoute(
                    path=f" ({func.__name__})",
                    endpoint=func,
                    name=func.__name__,
                    methods=["POST"],
                    response_model=callbacks,
                    dependencies=self.dependencies,
                    dependency_overrides_provider=self.dependency_overrides_provider,
                    tags=self.tags,
                ),
            )
            return func

        return decorator

    def fallback_bytes(self, func):
        """Handler to be called when the received message is not a text (but bytes). Will call `fallback` by default."""
        self._fallback_bytes = func
        return func

    def fallback(self, func):
        self._fallback = func
        return func

    async def _fallback_bytes(self, websocket: WebSocket):
        await self._fallback(websocket, None, KeyError("No text received"))


async def headerauth(x_token: Optional[str] = Header(None)):
    if x_token == "fail":
        raise HTTPException(status_code=400, detail="X-Token header invalid")


router = WSRouter(
    # discriminator="message_type",
    dependencies=[Depends(headerauth)],
    tags=["WS"],
    name="Websocket entrypoint",
    callbacks=Union[UserMessage, PostMessage],
)


@router.on_connect
async def on_connect(websocket: WebSocket):
    if "Fail" in websocket.scope["subprotocols"]:
        await websocket.close()
    else:
        await websocket.accept()


@router.fallback
async def fallback(websocket: WebSocket, message: str, error: ValidationError):
    await websocket.send_text("Invalid message type")


@router.fallback_bytes
async def fallback_bytes(websocket: WebSocket):
    await websocket.send_text("Bytes fallback")


@router.receive(UserMessage)
async def get_user_message(message: UserMessage, websocket: WebSocket):
    await websocket.send_json({"model": "UserMessage"})


@router.receive(PostMessage, callbacks=Union[UserMessage, PostMessage])
async def get_post_message(message: PostMessage, websocket: WebSocket):
    await websocket.send_json({"model": "PostMessage"})


app.include_router(router, prefix="/ws2")
