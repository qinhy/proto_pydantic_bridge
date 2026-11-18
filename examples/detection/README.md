# Detection demo with Protobuf, Pydantic, gRPC, and FastAPI

[protocol/detection.proto](protocol/detection.proto) defines the native `Detection` request, `DetectionResponse` response, and `DetectionService.Detect` RPC. The CLI and both servers use the same generated message classes. gRPC sends Protobuf binary, and the HTTP API accepts and returns ProtoJSON.

## Setup

From the repository root, use Python 3.10+ and install the demo dependencies with `uv`:

```sh
uv sync --extra demo
cd examples/detection
```

Run the remaining commands from `examples/detection`. In each new terminal, enter that directory first. The generated bindings are checked in.

## Try the three request paths

Start both servers in one terminal:

```sh
uv run --extra demo python run_servers.py
```

gRPC listens on `127.0.0.1:50051` and FastAPI listens on `127.0.0.1:8000`. Press Ctrl+C to stop both.

In a second terminal, send the same detection through each path:

```sh
uv run --extra demo python client.py --class-id 3
uv run --extra demo python client.py --transport http --backend local --class-id 3
uv run --extra demo python client.py --transport http --backend grpc --class-id 3
```

The CLI prints the response JSON, then the native response type and its serialized Protobuf size. Direct gRPC and HTTP forwarding report `processed_by: "grpc"`. Local HTTP processing reports `processed_by: "fastapi"`.

Use `--target HOST:PORT` to change the direct gRPC destination, which defaults to `127.0.0.1:50051`. Use `--url URL` to change the HTTP destination, which defaults to `http://127.0.0.1:8000/detect`. To change FastAPI’s upstream gRPC address, set `DETECTION_GRPC_TARGET` in the FastAPI server’s environment. It defaults to `127.0.0.1:50051`.

### Run either server on its own

Start gRPC for direct gRPC requests:

```sh
uv run --extra demo python -m server.grpc_server
```

Start FastAPI for HTTP local processing:

```sh
uv run --extra demo uvicorn server.fastapi_server:app --host 127.0.0.1 --port 8000
```

## HTTP API

Open [Swagger UI](http://127.0.0.1:8000/docs) to try the endpoint or inspect the [OpenAPI schema](http://127.0.0.1:8000/openapi.json). [GET /health](http://127.0.0.1:8000/health) returns the app status and configured gRPC target.

`POST /detect` requires a JSON object as the request body. The `backend` query parameter defaults to `local`. With `backend=grpc`, FastAPI forwards the validated native message to `DetectionService.Detect`.

```json
{
  "class_id": 3,
  "confidence": 0.95,
  "bbox": [10, 20, 100, 200],
  "image_id": "cam-001"
}
```

Both backends use [algorithm/processing.py](algorithm/processing.py). It requires a nonnegative class ID, finite confidence between 0 and 1, and either an empty bounding box or four finite coordinates in `[x1, y1, x2, y2]` order with `x2 >= x1` and `y2 >= y1`. This demo echoes each valid detection in a response with `total: 1`. Invalid detections return HTTP 422 or gRPC `INVALID_ARGUMENT`.

## Try the bridge directly

Importing `protocol.detection_pb2` calls `register_many(Detection, DetectionResponse)`. The generated classes then support Pydantic validation, serialization, and schema generation while retaining native Protobuf methods such as `SerializeToString()`.

```python
from protocol.detection_pb2 import Detection, DetectionResponse

request = Detection.model_validate({"class_id": 3, "confidence": 0.95})
response = DetectionResponse.model_validate(
    {"detections": [request.model_dump()], "total": 1}
)

assert type(response.detections[0]) is Detection
assert DetectionResponse.FromString(response.SerializeToString()) == response
```

Run [demos/bridge_demo.py](demos/bridge_demo.py) or [demos/detection_request_response.py](demos/detection_request_response.py) to see both native types inside a Pydantic `BaseModel`.

```sh
uv run --extra demo python -m demos.bridge_demo
```

## Regenerate bindings and run tests

After editing the schema, run [protocol/generate.py](protocol/generate.py) to regenerate `detection_pb2.py`, `detection_pb2.pyi`, and `detection_pb2_grpc.py`. The generator adds bridge registration to the message module and makes the gRPC binding’s sibling import package-relative.

```sh
uv run --extra demo python -m protocol.generate
```

Run the integration tests:

```sh
uv run --extra demo pytest -q
```

[The tests](tests/test_demo.py) cover native Protobuf and Pydantic round trips, direct gRPC and HTTP forwarding through a real gRPC server, HTTP local processing and OpenAPI, validation errors, and the client.
