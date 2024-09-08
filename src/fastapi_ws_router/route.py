from typing import (
    Callable,
    Optional,
    Sequence,
    Tuple,
    List,
)

from fastapi import Depends
from fastapi.routing import APIRoute, get_websocket_app
from starlette._exception_handler import wrap_app_handling_exceptions
from starlette.routing import WebSocketRoute, Match, websocket_session
from starlette.types import Scope, Receive, Send
from starlette.websockets import WebSocket


class WSMainRoute(APIRoute):
    def __init__(
        self,
        path: str,
        endpoint: Callable,
        name: Optional[str] = None,
        dependencies: Optional[Sequence[Depends]] = None,
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
            )
        )

    def matches(self, scope: Scope) -> Tuple[Match, Scope]:
        return WebSocketRoute.matches(self, scope)

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        session = WebSocket(scope, receive=receive, send=send)
        await wrap_app_handling_exceptions(self.app, session)(scope, receive, send)


class WSRoute(APIRoute):
    """This is a "mocked" route that never matches. It's there only for the documentation"""

    def matches(self, scope: Scope) -> Tuple[Match, Scope]:
        return Match.NONE, {}
