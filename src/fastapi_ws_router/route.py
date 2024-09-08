from collections.abc import Sequence
from enum import Enum
from typing import (
    Callable,
    List,
    Optional,
    Tuple,
    Union,
)

from fastapi import Depends
from fastapi.routing import APIRoute, get_websocket_app
from starlette._exception_handler import wrap_app_handling_exceptions  # noqa: PLC2701
from starlette.routing import Match, WebSocketRoute, websocket_session
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocket


class WSMainRoute(APIRoute):
    """
    Websocket entrypoint. This is the route that the client will be using to connect to the websocket endpoint.

    It is based on the regular HTTP api route (so that FastAPI would include it in the openapi),
    but it behaves as websocket route.
    """

    def __init__(
        self,
        path: str,
        endpoint: Callable,
        name: Optional[str] = None,
        dependencies: Optional[Sequence[Depends]] = None,  # type: ignore[valid-type]
        include_in_schema: bool = True,  # noqa: FBT001 FBT002
        dependency_overrides_provider: Optional[Callable] = None,
        response_model: Optional[type] = None,
        tags: Optional[List[Union[str, Enum]]] = None,
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
            )
        )

    def matches(self, scope: Scope) -> Tuple[Match, Scope]:
        return WebSocketRoute.matches(self, scope)  # type: ignore[arg-type]

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        session = WebSocket(scope, receive=receive, send=send)
        await wrap_app_handling_exceptions(self.app, session)(scope, receive, send)


class WSRoute(APIRoute):
    """This is a "mocked" route that never matches. It's there only for the documentation"""

    def matches(self, _: Scope) -> Tuple[Match, Scope]:  # noqa: PLR6301
        return Match.NONE, {}
