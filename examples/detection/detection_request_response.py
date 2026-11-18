"""Run after generating detection_pb2.py from examples/detection.proto.

python -m grpc_tools.protoc -I examples --python_out=examples --grpc_python_out=examples examples/detection.proto
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. detection.proto
PYTHONPATH=examples:. python examples/detection_request_response.py
"""
from pydantic import BaseModel, TypeAdapter
from detection_pb2 import Detection, DetectionResponse
from proto_pydantic_bridge import register_many

register_many(Detection, DetectionResponse)

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
# from detection_pb2_grpc import DetectionServiceStub
# result = DetectionServiceStub(channel).Detect(request)
# assert type(result) is DetectionResponse
