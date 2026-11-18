# proto-pydantic-bridge (prototype)

**Original generated Protobuf objects, Pydantic v2 validation/serialization integration, and unchanged native gRPC messages.** This is an experimental standalone library, **not published to PyPI**.

## Design goal

One `.proto` schema, one set of generated `_pb2` classes, no extra generated Pydantic model classes.

```text
.proto --protoc--> detection_pb2.Detection
                         |
                  Pydantic v2 adapter
                         |
              native detection_pb2.Detection
                   /             \
             gRPC (direct)     ZeroMQ (.SerializeToString())
```

## Install (from this source directory)

```bash
python -m pip install -e '.[test]'
```

The core library depends only on `pydantic` and `protobuf`. `pytest`, `FastAPI` are optional test dependencies; `grpcio` is used by the optional gRPC integration test.

To run the included tests:

```bash
python -m pip install grpcio
pytest -q
```

## Option A — non-invasive adapter (recommended)

```python
from pydantic import BaseModel, TypeAdapter
from google.protobuf.type_pb2 import Type  # replace with your generated Detection
from proto_pydantic_bridge import Proto

class Request(BaseModel):
    message: Proto[Type]

request = Request.model_validate({'message': {'name': 'demo.User'}})
assert type(request.message) is Type
assert Type.FromString(request.message.SerializeToString()) == request.message
print(request.model_dump())
print(Request.model_json_schema())

adapter = TypeAdapter(Proto[Type])
message = adapter.validate_python({'name': 'demo.User'})
```

### Option B — direct type annotations and Pydantic-style convenience methods

**Explicitly modifies the original class.** This is an unsupported extension point in Protobuf's Python implementation. Test and version-pin dependencies if using this in production.

```python
from google.protobuf.type_pb2 import Type
from pydantic import BaseModel
from proto_pydantic_bridge import register

register(Type)  # BEFORE building Pydantic/FastAPI models

class Envelope(BaseModel):
    message: Type

native = Type.model_validate({'name': 'demo.User'})
assert type(native) is Type
assert native.SerializeToString()
print(native.model_dump())

value = Envelope.model_validate({'message': {'name': 'demo.User'}})
assert type(value.message) is Type
```

### Register both request and response (including nested messages)

For a `.proto` defining `Detection` and `DetectionResponse` with `repeated Detection detections`:

```python
from pydantic import BaseModel
from detection_pb2 import Detection, DetectionResponse
from proto_pydantic_bridge import register_many

register_many(Detection, DetectionResponse)

request = Detection.model_validate({'class_id': 1, 'confidence': 0.95})
response = DetectionResponse.model_validate({
    'detections': [{'class_id': 1, 'confidence': 0.95}],
    'total': 1,
})
assert type(response) is DetectionResponse
assert type(response.detections[0]) is Detection

class Exchange(BaseModel):
    request: Detection
    response: DetectionResponse

print(Exchange(request=request, response=response).model_dump())
```

For a generated module with many message types, call `register_module(detection_pb2)` once before creating Pydantic models. The registration attaches Pydantic hooks to top-level message classes in that module. Nested Protobuf fields preserve their native types automatically; register those types too if you need their Pydantic-style instance methods.

The full **`examples/detection/`** demo contains `detection.proto`, generated message classes, real gRPC server/client, a FastAPI server with local or gRPC-backed handling, and integration tests. See [`examples/detection/README.md`](examples/detection/README.md). If you prefer to avoid patching, use `Proto[Detection]` and `Proto[DetectionResponse]` in your annotations.

You may use `register_module(your_pb2)` to register the top-level messages in a whole generated module.

## Full gRPC + FastAPI detection example

See [`examples/detection/README.md`](examples/detection/README.md) for a complete executable demo with a native gRPC server, a CLI, a FastAPI HTTP server and working forwarding to gRPC. The same original `Detection` and `DetectionResponse` message types are shared across both transports.

```bash
python -m pip install -e '.[demo]'
python examples/detection/generate.py  # optional; shipped with working _pb2 files
python examples/detection/grpc_server.py
# In another terminal:
uvicorn fastapi_server:app --app-dir examples/detection --port 8000
# In a third terminal:
python examples/detection/grpc_client.py --transport http --backend grpc
```

## FastAPI example

```python
from fastapi import FastAPI, Body
from google.protobuf.type_pb2 import Type
from proto_pydantic_bridge import register

register(Type)
app = FastAPI()

@app.post('/echo', response_model=Type)
def echo(message: Type = Body(...)) -> Type:
    return message
```

**Important:** Use `Body(...)` explicitly, or put a message into a regular `BaseModel` request. FastAPI may otherwise treat a custom `Message` type as a query parameter.

## Native gRPC compatibility

Native `_pb2` instances have unchanged `SerializeToString`, `FromString`, `ParseFromString`, and normal generated gRPC request/response compatibility.

```python
native = Type.model_validate({'name': 'demo.User'})  # after register(Type)
response = stub.Process(native)  # assuming matching generated RPC method
```

There is **no conversion back to Protobuf**. Pydantic validation is explicitly opt-in when you call the adapter or a Pydantic model, not on every field assignment to a protobuf object.

## Included tests

- Pydantic v2 `TypeAdapter` and nested `BaseModel`
- Native message identity and Protobuf binary round-trip
- Bytes fields (base64 in ProtoJSON) and uint64 fields (decimal JSON strings)
- Nested/repeated messages and string-keyed map fields
- Invalid-input errors
- FastAPI `/openapi.json` and HTTP request/response with explicit `Body`
- A **real localhost gRPC unary echo** using the original message class, without generated stub code
- End-to-end detection example with generated-style gRPC stub, CLI, FastAPI local and forwarding modes
- Whole-module opt-in registration

## Scope and limitations

1. **Prototype, not full Pydantic parity.** `model_validate` parses dicts through Protobuf's `json_format.ParseDict`. Pydantic constraints such as `Field(ge=0)` are **not applied** inside protobuf messages. Existing native instances are returned unchanged.
2. `model_dump` uses `MessageToDict`: this is the **ProtoJSON mapping**, not a Python-native representation. For example, bytes fields become base64 strings, 64-bit integers may become decimal strings, and absent fields are commonly omitted.
3. JSON schema is a *partial* descriptor-derived representation intended for normal messages. It expands nested messages, repeated fields, maps, enums and common scalar types. Recursive messages are represented with a conservative partial schema. Advanced well-known types (`Any`, `Struct`), `oneof` constraints, extensions, field aliases and proto2/editions rules need more work for schema fidelity.
4. The `register()` mode adds attributes to generated message classes. It can collide with application methods or break after an upstream protobuf upgrade; the `Proto[Message]` mode is safer and makes no modifications.
5. Pydantic model validation is not the same as validating an already populated protobuf instance against custom field rules. For that use case consider Protobuf-native validation such as Protovalidate.
6. Using the `register()` mode for FastAPI needs `Body(...)` to mark direct message parameters as request bodies, and large or complex OpenAPI schemas require deeper testing.
7. The library only adds a model/serialization bridge; it does **not** change Protobuf's binary wire format, enable zero-copy arrays, or introduce IPC or gRPC transport.
8. It is not a drop-in `BaseModel` implementation: Pydantic methods like `model_copy`, `model_fields`, and `model_dump_json` are not implemented.

## Version/testing note

Initial tests performed using Python 3.13, protobuf 6.33.6, Pydantic 2.13.5, grpcio 1.80.0, FastAPI 0.128.2. Broader cross-version CI is needed before distribution.
