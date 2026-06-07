from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class SolveRequest(_message.Message):
    __slots__ = ("image", "user_text", "session_id", "user_id")
    IMAGE_FIELD_NUMBER: _ClassVar[int]
    USER_TEXT_FIELD_NUMBER: _ClassVar[int]
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    image: bytes
    user_text: str
    session_id: str
    user_id: str
    def __init__(self, image: _Optional[bytes] = ..., user_text: _Optional[str] = ..., session_id: _Optional[str] = ..., user_id: _Optional[str] = ...) -> None: ...

class SolveChunk(_message.Message):
    __slots__ = ("type", "stage", "content")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    STAGE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    type: str
    stage: str
    content: str
    def __init__(self, type: _Optional[str] = ..., stage: _Optional[str] = ..., content: _Optional[str] = ...) -> None: ...

class HealthRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HealthReply(_message.Message):
    __slots__ = ("status",)
    STATUS_FIELD_NUMBER: _ClassVar[int]
    status: str
    def __init__(self, status: _Optional[str] = ...) -> None: ...
