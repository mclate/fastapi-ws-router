from enum import Enum
from types import GenericAlias
from typing import (
    Callable,
    Optional,
    Sequence,
    List,
    Awaitable,
)
from typing import (
    Dict,
    Union,
    Annotated,
    Any,
    Type,
)

from fastapi import params
from fastapi.routing import APIRouter
from pydantic import BaseModel, TypeAdapter, Field, ValidationError
from starlette.types import Lifespan
from starlette.websockets import WebSocket, WebSocketDisconnect
from typing_extensions import Doc

from .route import WSRoute, WSMainRoute


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
        dispatcher: Callable[[WebSocket, Dict[type, Callable], str], Awaitable[None]] = None,
        as_text: bool = True,
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
        self.dispatcher = dispatcher or self._dispatcher
        self.mapping: Dict[type, Callable] = {}
        self.as_text = as_text
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

    def _build_adapter(self) -> Optional[TypeAdapter]:
        if not self.mapping:
            return None
        models = GenericAlias(Union, tuple(self.mapping.keys()))
        AnnotatedModels = Annotated[models, Field(discriminator=self.discriminator)]
        return TypeAdapter(AnnotatedModels)

    async def handler(self, websocket: WebSocket):
        if not self._adapter:
            self._adapter = self._build_adapter()

        await self._on_connect(websocket)

        try:
            if self.as_text:
                message = await websocket.receive_text()
            else:
                message = await websocket.receive_bytes()
        except WebSocketDisconnect as err:
            await self._on_disconnect(websocket, err.code, err.reason)
            return
        except RuntimeError as err:
            await self._fallback(websocket, None, err)
            return

        await self.dispatcher(websocket, self.mapping, message)

    async def _dispatcher(
        self,
        websocket: WebSocket,
        mapping: Dict[type, Callable],
        message: str,
    ):
        try:
            if not self._adapter:
                await self._fallback(websocket, message, None)
                return
            validated = self._adapter.validate_json(message)
        except ValidationError as e:
            await self._fallback(websocket, message, e)
            return

        handler = mapping[validated.__class__]
        await handler(websocket, validated)

    async def _on_disconnect(self, websocket: WebSocket, code: int, message: Optional[str]) -> None:
        """Override to handle client disconnect"""
        pass

    def on_disconnect(self, func):
        self._on_disconnect = func
        return func

    async def _on_connect(self, websocket: WebSocket) -> None:
        """Override to handle an incoming websocket connection"""
        await websocket.accept()

    def on_connect(self, func):
        self._on_connect = func
        return func

    def receive(self, model: Type[BaseModel], /, callbacks: Union[Type[BaseModel]] = None, path: str = None):
        def decorator(func):
            self.mapping[model] = func
            self.routes.append(
                WSRoute(
                    path=path if path is not None else f" ({func.__name__})",
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

    async def _fallback(
        self,
        websocket: WebSocket,
        message: Optional[Union[str, bytes]],
        error: ValidationError,
    ):
        """Handler to be called when the received message is not a valid model."""
        pass

    def fallback(self, func):
        self._fallback = func
        return func
