"""Integration tests for the detection example.

Run from repository root: pytest -q examples/detection/tests/test_demo.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import grpc
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, TypeAdapter

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from client import call_grpc, call_http
from protocol.detection_pb2 import Detection, DetectionResponse
from server.fastapi_server import app
from server.grpc_server import start_server


@pytest.fixture
def server():
    running, port = start_server(port=0)
    try:
        yield f"127.0.0.1:{port}"
    finally:
        running.stop(grace=0).wait(timeout=5)


def request(class_id: int = 1) -> Detection:
    return Detection.model_validate({
        "class_id": class_id, "confidence": 0.95,
        "bbox": [10, 20, 100, 200], "image_id": "camera-001",
    })


def test_same_original_protobuf_classes_support_pydantic_and_binary():
    msg = request()
    assert type(msg) is Detection
    assert TypeAdapter(Detection).validate_python(msg) is msg
    assert type(Detection.FromString(msg.SerializeToString())) is Detection

    class Envelope(BaseModel):
        request: Detection
        response: DetectionResponse

    env = Envelope.model_validate({
        "request": msg,
        "response": {"detections": [msg.model_dump()], "total": 1},
    })
    assert type(env.response) is DetectionResponse
    assert type(env.response.detections[0]) is Detection
    assert DetectionResponse.FromString(env.response.SerializeToString()) == env.response
    assert Envelope.model_json_schema()["properties"]["request"]["type"] == "object"


def test_real_native_generated_grpc_stub(server):
    res = call_grpc(request(), target=server)
    assert type(res) is DetectionResponse
    assert type(res.detections[0]) is Detection
    assert res.total == 1
    assert res.processed_by == "grpc"
    assert res.detections[0].bbox[0] == 10
    assert res.detections[0].image_id == "camera-001"
    assert "processed_by" in res.model_dump()


def test_grpc_domain_error(server):
    with pytest.raises(grpc.RpcError) as raised:
        call_grpc(request(-1), target=server)
    assert raised.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_fastapi_local_backend_and_openapi():
    client = TestClient(app)
    response = client.post("/detect?backend=local", json=request().model_dump())
    assert response.status_code == 200, response.text
    value = DetectionResponse.model_validate(response.json())
    assert type(value) is DetectionResponse
    assert type(value.detections[0]) is Detection
    assert value.processed_by == "fastapi"
    assert value.total == 1
    assert client.get("/health").json()["status"] == "ok"
    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200, openapi.text
    assert "/detect" in openapi.json()["paths"]
    schema = openapi.json()["paths"]["/detect"]["post"]
    assert "requestBody" in schema and "responses" in schema


def test_fastapi_forward_to_actual_grpc(monkeypatch, server):
    monkeypatch.setenv("DETECTION_GRPC_TARGET", server)
    client = TestClient(app)
    response = client.post("/detect?backend=grpc", json=request(9).model_dump())
    assert response.status_code == 200, response.text
    value = DetectionResponse.model_validate(response.json())
    assert type(value) is DetectionResponse
    assert value.processed_by == "grpc"
    assert value.detections[0].class_id == 9


def test_local_and_grpc_domain_errors(monkeypatch, server):
    monkeypatch.setenv("DETECTION_GRPC_TARGET", server)
    with TestClient(app) as client:
        for backend in ("local", "grpc"):
            bad = client.post(f"/detect?backend={backend}", json=request(-1).model_dump())
            assert bad.status_code == 422, bad.text
        bad_json = client.post("/detect", json={"not_a_protobuf_field": 100})
        assert bad_json.status_code == 422, bad_json.text
        bad_backend = client.post("/detect?backend=unsupported", json=request().model_dump())
        assert bad_backend.status_code == 422


def test_real_cli_grpc(server):
    location = Path(__file__).resolve().parents[1] / "client.py"
    command = [sys.executable, str(location), "--target", server, "--class-id", "7"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=12)
    assert result.returncode == 0, result.stderr
    assert '"class_id": 7' in result.stdout
    assert "native_type=DetectionResponse" in result.stdout


def test_http_client_converts_response_to_native_protobuf(monkeypatch):
    """Test the urllib HTTP client path without opening a separate HTTP port."""
    import client

    class FakeHTTPResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({"total": 1, "processed_by": "fastapi", "detections": [{"class_id": 5}]}).encode()

    def fake_urlopen(req, timeout):
        assert req.method == "POST"
        assert "backend=local" in req.full_url
        assert json.loads(req.data)["class_id"] == 5
        return FakeHTTPResponse()

    monkeypatch.setattr(client.urllib_request, "urlopen", fake_urlopen)
    res = call_http(request(5))
    assert type(res) is DetectionResponse
    assert type(res.detections[0]) is Detection
    assert res.total == 1
