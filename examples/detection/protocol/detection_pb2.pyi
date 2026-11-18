from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class DetectionServerConfig(_message.Message):
    __slots__ = ("host", "grpc_port", "fastapi_port")
    HOST_FIELD_NUMBER: _ClassVar[int]
    GRPC_PORT_FIELD_NUMBER: _ClassVar[int]
    FASTAPI_PORT_FIELD_NUMBER: _ClassVar[int]
    host: str
    grpc_port: int
    fastapi_port: int
    def __init__(self, host: _Optional[str] = ..., grpc_port: _Optional[int] = ..., fastapi_port: _Optional[int] = ...) -> None: ...

class Detection(_message.Message):
    __slots__ = ("class_id", "confidence", "bbox", "image_id")
    CLASS_ID_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    BBOX_FIELD_NUMBER: _ClassVar[int]
    IMAGE_ID_FIELD_NUMBER: _ClassVar[int]
    class_id: int
    confidence: float
    bbox: _containers.RepeatedScalarFieldContainer[float]
    image_id: str
    def __init__(self, class_id: _Optional[int] = ..., confidence: _Optional[float] = ..., bbox: _Optional[_Iterable[float]] = ..., image_id: _Optional[str] = ...) -> None: ...

class DetectionResponse(_message.Message):
    __slots__ = ("detections", "total", "processed_by", "message")
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    PROCESSED_BY_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    detections: _containers.RepeatedCompositeFieldContainer[Detection]
    total: int
    processed_by: str
    message: str
    def __init__(self, detections: _Optional[_Iterable[_Union[Detection, _Mapping]]] = ..., total: _Optional[int] = ..., processed_by: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...
