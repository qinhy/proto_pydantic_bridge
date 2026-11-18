"""Single processing function shared by the HTTP and gRPC servers.

This is an intentionally simple deterministic demo. Add inference here later.
"""
from __future__ import annotations

import math

from protocol.detection_pb2 import Detection, DetectionResponse


class InvalidDetection(ValueError):
    """Domain-validation error (separate from protobuf's type validation)."""


def process_detection(request: Detection, *, processed_by: str) -> DetectionResponse:
    """Return a native protobuf response, preserving all request values."""
    if not isinstance(request, Detection):
        raise TypeError("request must be the native protocol.detection_pb2.Detection")
    if request.class_id < 0:
        raise InvalidDetection("class_id must be >= 0")
    if not math.isfinite(request.confidence) or not 0 <= request.confidence <= 1:
        raise InvalidDetection("confidence must be finite and between 0 and 1")
    if len(request.bbox) not in (0, 4):
        raise InvalidDetection("bbox must be empty or have exactly 4 coordinates")
    if any(not math.isfinite(v) for v in request.bbox):
        raise InvalidDetection("bbox must contain only finite numbers")
    if len(request.bbox) == 4 and (request.bbox[2] < request.bbox[0] or request.bbox[3] < request.bbox[1]):
        raise InvalidDetection("bbox must satisfy x2 >= x1 and y2 >= y1")

    # Protobuf construction, not conversion to or from a second Pydantic model.
    return DetectionResponse(
        detections=[request],
        total=1,
        processed_by=processed_by,
        message=f"Processed class_id={request.class_id} (image_id={request.image_id or 'none'})",
    )
