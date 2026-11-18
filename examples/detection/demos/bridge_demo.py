"""Shows that both generated request and response support Pydantic APIs."""
from pathlib import Path
import sys

from pydantic import BaseModel, TypeAdapter

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


from protocol.detection_pb2 import Detection, DetectionResponse


class Exchange(BaseModel):
    request: Detection
    response: DetectionResponse


def main() -> None:
    request = Detection.model_validate({"class_id": 1, "confidence": 0.95})
    response = DetectionResponse.model_validate({
        "detections": [{"class_id": 1, "confidence": 0.95}],
        "total": 1,
        "processed_by": "example",
    })
    envelope = Exchange.model_validate({"request": request, "response": response})
    assert type(envelope.request) is Detection
    assert type(envelope.response) is DetectionResponse
    assert type(envelope.response.detections[0]) is Detection
    assert TypeAdapter(DetectionResponse).validate_python(response) is response
    assert DetectionResponse.FromString(response.SerializeToString()) == response
    print(envelope.model_dump())
    print(Exchange.model_json_schema())


if __name__ == "__main__":
    main()
