# FastAPI WebSocker router

[![PyPI - Version](https://img.shields.io/pypi/v/fastapi-ws-router.svg)](https://pypi.org/project/fastapi-ws-router)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/fastapi-ws-router.svg)](https://pypi.org/project/fastapi-ws-router)

-----

Small library that allows one to document WebSocket messages in FastAPI.

## Overview

This library allows you to define websocket event handlers in the similar way one would define regular api endpoints. We
take somewhat opinionated approach and assume that all your events will confront to some PyDantic models, and it will be
possible to discriminate between them (preferably, based on some field. We use `pydantic.TypeAdapter` for this).

Library will make sure to generate OpenAPI documentation for your WebSocket handlers in a form of regular HTTP POST
endpoints. Because OpenAPI doesn't have any specifications for WebSockets, we have to bend some rules and use regular
routes to document possible WebSocket messages. See "OpenAPI limitations" section for more details.

## What this library does:

1. Provides somewhat opinionated way to document WebSocket endpoints in FastAPI.
2. Takes care of routing websocket messages to the corresponding handlers in the FastAPI-native way
3. Allows one to natively use PyDantic models to define WebSocket message schemas
4. Allows one to (somewhat) natively use FastAPI dependency injection

## What this library does not:

1. It doesn't take care of WebSockets management
2. It doesn't provide any kind of WebSocket server or client management
3. It doesn't handle any communications for you

In other words, you still have to take care of all the WebSocket operations you would normally do.

## Usage

Installation as usual:

```bash
pip install fastapi-ws-router
```

Then you can use it in your FastAPI application:

```python
from typing import Literal, Union

from fastapi import FastAPI
from fastapi_ws_router import WSRouter
from pydantic import BaseModel


# Messages we are expecting to receive defined as PyDantic models
class ChatMessage(BaseModel):
    action: Literal["message"]
    message: str


class ChatActivity(BaseModel):
    action: Literal["activity"]
    activity: str


app = FastAPI()

# Router to handle WebSocket connection
router = WSRouter(discriminator="action")  # Discriminator is optional


# Handlers for specific messages
@router.receive(ChatMessage, callbacks=Union[ChatMessage, ChatActivity])
async def on_chat_message(websocket, data: ChatMessage):
    await websocket.send_text(f"Got message: {data.message}")


@router.receive(ChatActivity)
async def on_chat_activity(websocket, data: ChatActivity):
    await websocket.send_text(f"Got activity: {data.activity}")


# Finally, include the router in your FastAPI app (this should be the last step)
app.include_router(router, prefix="/ws")

```

![OpenAPI example](https://github.com/mclate/fastapi-ws-router/blob/main/example.png)

In the example we use `action` field as a discriminator, although the message structure is completely up to
you. `discriminator` property is optional, it will help PyDantic to perform some optimizations

## Documenting server-side events

In cases when the WebSocket communication is bidirectional or server is emitting events, it can be desired to inform the
client what messages to expect. This can be achieved by providing a model(s) to the  `callbacks` parameter.

```python

class Event1(BaseModel):
    ...


class Event2(BaseModel):
    ...


class Event3(BaseModel):
    ...


router = WSRouter(callbacks=Union[Event1, Event2])


@router.receive(Event1, callbacks=Union[Event2, Event3])
async def on_event1(websocket, data: Event1):
    ...

```

⚠️ Notice that those callbacks are informational only and pose no effect or restriction on the actual communication.
Server doesn't have to comply with them at all. They are there only for the documentation.

Callbacks defined in the router will be shown in the entrypoint route. This is to indicate that "once connected, client
can expect to receive these messages"

Callbacks defined on the event handlers will be shown in the corresponding route. This is to indicate that "once this
event is received, client can expect to receive these messages".

There is no "predefined" place to put events that are emitted by the server without any user interactions. It's up to
you to decide where to put them. Router callbacks might be a good place for that.

## WebSockets limitation

### Event handlers

This is the only thing we are somewhat opinionated about: event handler will always accept a single message being a
PyDantic model built from the received ws message (one message - one model instance).

Notice, that this doesn't apply to the messages emitted by the server. The library helps document them based on PyDantic
models, but it doesn't interfere with the actual communication in any way.

Event handler should always have next signature: `async def handler(WebSocket, BaseModel)`  (first argument is always
a `WebSocket` instance and the second one is a PyDantic model instance)

Not-async handlers are not supported.

### Dependency injection

Due to the nature of WebSockets, only the entrypoint route (defined by the `WSRouter` itself) is able to apply
dependency injection. In other words, it is not possible to use any dependencies or `Path/Query/Header/Body` parameters
in the event handlers.

There is a way to pass down the data from the entrypoint to the handlers using the underlying `websocket.scope` object.
Below is an example of how one can pass the path parameter to the event handler:

```python
async def path_depends(
    websocket: WebSocket,
    item: str = Path(...),  # This is a regular FastAPI dependency, everything is possible here
):
    websocket.scope["path_item"] = item


router = WSRouter(dependencies=[Depends(path)])  # Inject dependency in the router
app.include_router(router, prefix="/ws/{item}")  # Attach router to a parametrized path


@router.receive(ChatMessage)
async def on_chat_message(websocket: WebSocket, data: ChatMessage):
    path_item = websocket.scope["path_item"]  # Fetch path parameter from the scope
    ...
```

### Subroutes

It is not possible to attach or include any subroutes in the WebSocket route. However, one can have multiple `WSRouter`
instances attached to different paths.

## OpenAPI limitations

Currently, OpenAPI doesn't have any specification for the WebSockets. In order to include WebSocket events in the
documentation we ~~abuse~~ reuse regular `POST` endpoints.

These endpoints will have "weird" path (router prefix + handler name) - this provides some better visibility in the
documentation. Such routes, when attempted to be accessed directly, say, through the Swagegr UI, will never be found, as
they are not a real routes. (In reality, they are, they just "tweaked" to never match any path given)

It is possible to override path of each handler by providing `path` parameter in the `receive` decorator. It will be
appended to the router prefix. This path can be anything - handler routes are guaranteed to never match and requested
path. This is only for documentation purpose.

```python
router = WSRouter()
app.include_router(router, prefix="/ws")


@router.receive(ChatMessage, path=": WS Chat message")  # Result in `/ws: WS Chat message` path in the documentation
async def on_chat_message(websocket, data: ChatMessage):
    ...
```

You can disable custom path by setting `path=""`.

WebSockets don't have a notion of a "response" similar to the http protocol, thus, by default, there will be no response
body in the OpenAPI specification. This can be modified with the `callbacks` parameter

We also do not support any status codes or response headers.

## Connection handlers

Connection handlers are exposed as decorators similar to the event handlers.

### `on_connect`

Emitted when a new WebSocket connection is established. Typically, this is where you determine whether to allow new
client to connect.

```python

@router.on_connect
async def on_connect(websocket: WebSocket):
    # One must call either accept or close on the websocket
    await websocket.accept()
```

### `on_disconnect`

Emitted when a WebSocket connection is closed by the client.

```python

@router.on_disconnect
async def on_disconnect(websocket: WebSocket, message: WebSocketDisconnect):
    del my_connected_clients[websocket]  # I.e., remove the client from the list of connected clients
```

### `on_fallback`

Emitted when we are unable to cast message to any of the known PyDantic models or there is a violation of the WebSocket
protocol. Message will be `None` in case of protocol violation. You will receive the original error in the third
parameter of the handler. `message` will always be either a string or bytes (based on what protocol you define in
the `WSRouter`)

In case of validation error, you will receive original PyDantic `ValidationError` as a third parameter.

```python

@router.on_fallback
async def on_fallback(websocket: WebSocket, message: Optional[Union[str, bytes]], err: Optional[Exception]):
    ...

```

## Dispatcher

It is possible to override the default dispatching behaviour. This might be needed in cases when you have a more
complicated handler selection logic.

`mapping` is a dict that contains all registered models mapping to the corresponding handlers. `message` is a raw
message received from the client (always `str` or `bytes`)

As the outcome, dispatcher most likely will call one of the handlers with the `websocket` and the deserialized message.

```python

# As we now use custom dispatcher, we can ignore the model assumption and use whatever we want in the arguments
# Be aware that this handler will still be inspected by FastAPI in order to build a documentation, so make sure that the arguments are "pydantic-compatible"
async def left_handler(websocket: WebSocket, message: str):
    print("Left", message)


async def right_handler(websocket: WebSocket, message: str):
    print("Right", message)


async def dispatcher(websocket: WebSocket, mapping: dict, message: str):
    if message.startswith("LEFT-"):
        await left_handler(websocket, message[5:])
    else:
        await right_handler(websocket, message[6:])


router = WSRouter(dispatcher=dispatcher)
app.include_router(router, prefix="/ws")

```

## Binary mode

By default, router assumes that messages are strings and use `websocket.receive_text()`.
It is possible to switch to bytes mode by providing `as_text=False` to the `WSRouter` constructor.
In this case `websocket.receive_bytes()` will be used instead.
In default dispatcher, received bytes will be sent to the PyDantic `TypeAdapter.validate_json` method.

## License

`fastapi-ws-router` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
