"""Register native generated protobuf message classes with Pydantic v2.

Call this module BEFORE defining a Pydantic/FastAPI endpoint with Detection
or DetectionResponse in its annotations. Registration does not wrap the objects.
"""
from detection_pb2 import Detection, DetectionResponse
from proto_pydantic_bridge import register_many

register_many(Detection, DetectionResponse)

__all__ = ["Detection", "DetectionResponse"]
