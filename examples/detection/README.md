# Detection end-to-end demo: Protobuf + Pydantic + gRPC + FastAPI

One `.proto` definition; two **original generated** message classes: `Detection` and `DetectionResponse`. Both are Pydantic-compatible after `register_many`, and both remain native Protobuf classes for standard gRPC. The REST API uses ProtoJSON with the same types for request/response.

## Files

```text
examples/detection/
├── detection.proto        # Request, response, service — single schema
├── generate.py            # Official grpc_tools.protoc code generation
├── detection_pb2.py       # Checked-in native Protobuf message classes
├── detection_pb2.pyi      # Type hints (regenerate using generate.py)
├── detection_pb2_grpc.py  # Checked-in gRPC client/server bindings
├── bridge_models.py       # Registers BOTH message types for Pydantic
├── processing.py          # Processing + domain validation, used by both servers
├── grpc_server.py         # Full gRPC unary server
├── grpc_client.py         # CLI client for gRPC AND HTTP
├── fastapi_server.py      # POST /detect?backend=local|grpc, GET /health
├── bridge_demo.py         # Pydantic model, native wire compatibility
├── test_demo.py           # Real gRPC + FastAPI integration tests
├── requirements.txt
└── README.md
```

## Setup

Python 3.10+ from the **repository root**:

```bash
python -m pip install -e '.[demo]'
```

On Windows PowerShell, the same command works. The package is a demo, not a published PyPI distribution.

To regenerate the `*_pb2.py`, `.pyi` and `*_pb2_grpc.py` code after editing `detection.proto`:

```bash
python examples/detection/generate.py
```

This requires `grpcio-tools` (included in the `demo` extra). These checked-in stubs work without regeneration. The message definitions were built from the `detection.proto` descriptor, and the gRPC bindings follow the generated plugin API; regeneration with the current official `grpcio-tools` is the authoritative way to update them.

## A. gRPC server + CLI client

**Terminal 1** — start the gRPC server:

```bash
python examples/detection/grpc_server.py --host 127.0.0.1 --port 50051
```

**Terminal 2** — send a native `_pb2.Detection` using the generated gRPC stub:

```bash
python examples/detection/grpc_client.py \
  --class-id 3 --confidence 0.95 \
  --bbox 10 20 100 200 --image-id cam-001
```

PowerShell one-line equivalent:

```powershell
python examples/detection/grpc_client.py --class-id 3 --confidence 0.95 --bbox 10 20 100 200 --image-id cam-001
```

Expected JSON response (float rounding may vary):

```json
{
  "detections": [{"class_id": 3, "confidence": 0.95, "bbox": [10, 20, 100, 200], "image_id": "cam-001"}],
  "total": 1,
  "processed_by": "grpc",
  "message": "Processed class_id=3 (image_id=cam-001)"
}
```

## B. FastAPI server: local processing OR forwarding to gRPC

**Terminal 3** — start FastAPI; keep the gRPC server running for forwarding:

```bash
uvicorn fastapi_server:app --app-dir examples/detection --host 127.0.0.1 --port 8000
```

Open interactive OpenAPI docs at **http://127.0.0.1:8000/docs**.

Both HTTP modes accept the **exact same JSON request** and return the same `DetectionResponse` schema:

```json
{
  "class_id": 3,
  "confidence": 0.95,
  "bbox": [10, 20, 100, 200],
  "image_id": "cam-001"
}
```

### B1. FastAPI processes locally (does not require gRPC)

```bash
python examples/detection/grpc_client.py --transport http --backend local --class-id 3
```

Or with curl:

```bash
curl -X POST 'http://127.0.0.1:8000/detect?backend=local' \
  -H 'Content-Type: application/json' \
  -d '{"class_id":3,"confidence":0.95,"bbox":[10,20,100,200],"image_id":"cam-001"}'
```

Returns `processed_by: "fastapi"`.

### B2. FastAPI forwards the ORIGINAL Protobuf object to gRPC

```bash
python examples/detection/grpc_client.py --transport http --backend grpc --class-id 3
```

Or:

```bash
curl -X POST 'http://127.0.0.1:8000/detect?backend=grpc' \
  -H 'Content-Type: application/json' \
  -d '{"class_id":3,"confidence":0.95,"bbox":[10,20,100,200],"image_id":"cam-001"}'
```

Returns `processed_by: "grpc"`. Change the upstream target if needed:

```bash
DETECTION_GRPC_TARGET=127.0.0.1:50051 uvicorn fastapi_server:app --app-dir examples/detection --port 8000
```

PowerShell: `$env:DETECTION_GRPC_TARGET="127.0.0.1:50051"` before running uvicorn.

## Data flow

```text
                          detection.proto
                                │
                             protoc
                                │
                     detection_pb2.py
                     detection_pb2_grpc.py
                                │
                     register_many(Detection,
                                   DetectionResponse)
                                │
         ┌──────────────────────┴───────────────────────┐
         │                                              │
  CLI gRPC client                                 HTTP JSON client
         │                                              │
  Detection (pb2)                                  FastAPI POST /detect
         │                                              │
         │                                     Detection (native pb2)
         │                                              │
         │                                 ┌────────────┴────────────┐
         │                           backend=local             backend=grpc
         │                                 │                         │
         │                           process_detection         gRPC Stub.Detect
         │                                 │                         │
         └── gRPC Server ── process_detection ────────┘             │
                  │                                                 │
              DetectionResponse (native pb2) ◄──────────────────────┘
                                │
                    HTTP serialization via Pydantic
                       or gRPC Protobuf wire bytes
```

## Why the bridge matters

```python
from bridge_models import Detection, DetectionResponse
from pydantic import BaseModel

req = Detection.model_validate({"class_id": 1, "confidence": 0.9})
assert type(req) is Detection
assert type(req.SerializeToString()) is bytes

resp = DetectionResponse.model_validate({"detections": [{"class_id": 1}], "total": 1})
assert type(resp.detections[0]) is Detection

class Exchange(BaseModel):
    request: Detection
    response: DetectionResponse

assert type(Exchange.model_validate({"request": req, "response": resp}).response) is DetectionResponse
```

## Run tests

```bash
pytest -q examples/detection/test_demo.py
pytest -q
```

Tests launch a real ephemeral-port gRPC server and call it using generated stubs, test FastAPI `local` and `grpc` modes, `/openapi.json`, invalid messages, and the CLI. The HTTP client encoder is also tested.

## Notes / safety / limitations

- This demo uses **insecure gRPC** and HTTP for localhost testing only. Use TLS, authentication, authorization and limits for remote deployment.
- The `register_many` path modifies the generated classes at runtime, an experimental extension point. It does **not** turn a Protobuf message into a subclass of `pydantic.BaseModel`.
- Pydantic integration uses standard ProtoJSON. For example 64-bit integers are often strings in HTTP JSON; protobuf binary over gRPC retains native wire semantics.
- `Field(...)` constraints are not applied automatically to native messages. The `processing.py` function demonstrates explicit domain validation (confidence, class ID, bbox).
- HTTP and gRPC share the Protobuf *schema* and native application objects. HTTP sends JSON; gRPC sends Protobuf binary. They are not byte-for-byte the same transport.
- `register_many` must run **before FastAPI generates route schemas**; `bridge_models.py` handles this.
- The synchronous gRPC call in FastAPI runs inside a `def` endpoint (FastAPI threadpool) and has a 3-second deadline. This is appropriate for a small demo; tune pooling/deadlines for production.
