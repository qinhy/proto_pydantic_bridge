"""Run after generating protocol/detection_pb2.py from protocol/detection.proto.

python examples/detection/protocol/generate.py
python examples/detection/demos/detection_request_response.py
"""
from pathlib import Path
import sys

from pydantic import BaseModel, TypeAdapter

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from protocol.detection_pb2 import Detection, DetectionResponse

request = Detection.model_validate({'class_id': 1, 'confidence': 0.95})
response = DetectionResponse.model_validate({
    'detections': [{'class_id': 1, 'confidence': 0.95}],
    'total': 1,
})


class Exchange(BaseModel):
    request: Detection
    response: DetectionResponse


exchange = Exchange.model_validate({'request': request, 'response': response})
assert type(exchange.request) is Detection
assert type(exchange.response) is DetectionResponse
assert type(exchange.response.detections[0]) is Detection

assert TypeAdapter(DetectionResponse).validate_python(response) is response
assert DetectionResponse.FromString(response.SerializeToString()) == response

print(exchange.model_dump())
print(Exchange.model_json_schema())
# Native gRPC, if a server is running:
# from protocol.detection_pb2_grpc import DetectionServiceStub
# result = DetectionServiceStub(channel).Detect(request)
# assert type(result) is DetectionResponse
