from typing import Literal, List, Union, Dict

from fastapi import FastAPI, Depends, Path
from pydantic import BaseModel
from starlette.requests import Request
from starlette.websockets import WebSocket

from fastapi_ws_router import WSRouter

app = FastAPI()


class User(BaseModel):
    user_name: str
    status: str


USERS: Dict[WebSocket, User] = {}


class RoomDetailsEvent(BaseModel):
    """Sent by the server when the user connects to the room"""

    action: Literal["server_room_details"]
    room_name: str


class UserJoinAction(User):
    """Sent by the user when he joins the room"""

    action: Literal["client_user_join"]


class UserJoinEvent(BaseModel):
    """Sent by the server all the users in the room to inform about the newly joined user"""

    action: Literal["server_user_join"]
    user: User


class PendingMessagesEvent(BaseModel):
    """Sent by the server to the newly joined user to inform about the pending messages"""

    action: Literal["server_pending_messages"]
    messages: List[str]


class ListUsersEvent(BaseModel):
    """Sent by the server the newly joined user"""

    action: Literal["server_users_list"]
    users: List[User]


class UserLeaveEvent(BaseModel):
    """Sent by the server to all users when someone is leaving the room"""

    action: Literal["server_user_leave"]
    room_id: str
    user: User


class UserMessageAction(BaseModel):
    """Sent by the user when he sends a message"""

    action: Literal["client_user_message"]
    message: str


class UserMessageEvent(BaseModel):
    """Sent by the server to all users when someone sends a message"""

    action: Literal["server_user_message"]
    room_id: str
    user: User
    message: str


async def room_id_depends(
    request: Request,
    room_id: str = Path(..., description="ID of the room to join"),
):
    """This is how we can pass the room_id from the path to the ws handlers"""
    request.scope["room_id"] = room_id


router = WSRouter(
    # discriminator="message_type",
    tags=["WS"],
    name="Websocket entrypoint",
    dependencies=[Depends(room_id_depends)],
    callbacks=RoomDetailsEvent,  # These are the events that user can expect once the connection is established
)


async def broadcast(room_id: str, event: BaseModel):
    """Broadcasts the event to all users in the room"""
    pass  # This is for the client to implement


@router.on_connect
async def connect(websocket: WebSocket):
    room_id = websocket.scope["room_id"]
    if room_id == "1":
        await websocket.accept()
        await websocket.send_json(
            RoomDetailsEvent(action="server_room_details", room_name="Room 1")
        )
    else:
        await websocket.close()


@router.on_disconnect
async def disconnect(websocket: WebSocket, code: int, message: str):
    room_id = websocket.scope["room_id"]

    await broadcast(room_id, UserLeaveEvent(action="server_user_leave", room_id=room_id, user=USERS[websocket]))


@router.receive(UserJoinAction, callbacks=Union[ListUsersEvent, PendingMessagesEvent])
async def user_join(message: UserJoinAction, websocket: WebSocket):
    room_id = websocket.scope["room_id"]
    user = User(user_name=message.user_name, status="active")
    USERS[websocket] = user
    await websocket.send_json(UserJoinEvent(action="server_user_join", user=user))
    await broadcast(room_id, ListUsersEvent(action="server_users_list", users=[user]))


@router.receive(UserMessageAction, callbacks=UserMessageEvent)
async def user_message(message: UserMessageAction, websocket: WebSocket):
    room_id = websocket.scope["room_id"]
    user = USERS[websocket]
    event = UserMessageEvent(
        action="server_user_message",
        room_id=room_id,
        user=user,
        message=message.message,
    )
    await broadcast(room_id, event)


app.include_router(router, prefix="/ws/{room_id:str}")
