"""FastAPI with a native protobuf request and native protobuf response.

Run: uvicorn server.fastapi_server:app --app-dir examples/detection --port 8000
Try: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Annotated, Literal

import grpc
from fastapi import Body, FastAPI, HTTPException, Query

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Imports/registers Pydantic core schemas BEFORE FastAPI inspects signatures.
from protocol.detection_pb2 import Detection, DetectionResponse

from protocol.detection_pb2_grpc import DetectionServiceStub
from algorithm.processing import InvalidDetection, process_detection

app = FastAPI(
    title="Detection: native Protobuf + Pydantic + FastAPI + gRPC",
    description="Same `_pb2.Detection` request and `_pb2.DetectionResponse` response over HTTP or gRPC.",
    version="1.0.0",
)


@app.get("/health")
def health():
    return {"status": "ok", "grpc_target": os.getenv("DETECTION_GRPC_TARGET", "127.0.0.1:50051")}


@app.post("/detect", response_model=DetectionResponse, tags=["detection"])
def detect(
    request: Detection = Detection(**{
                                    "class_id": 3,
                                    "confidence": 0.95,
                                    "bbox": [10, 20, 100, 200],
                                    "image_id": "cam-001"
                                    }),
    backend: Literal["local", "grpc"] = Query("local", description="Handle here or forward original protobuf to gRPC"),
) -> DetectionResponse:
    """FastAPI validates ProtoJSON then receives the original native protobuf object."""
    assert type(request) is Detection

    if backend == "local":
        try:
            return process_detection(request, processed_by="fastapi")
        except InvalidDetection as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    target = os.getenv("DETECTION_GRPC_TARGET", "127.0.0.1:50051")
    try:
        with grpc.insecure_channel(target) as channel:
            # request is ALREADY a native protobuf, no conversion back required.
            result = DetectionServiceStub(channel).Detect(request, timeout=3)
        assert type(result) is DetectionResponse
        return result
    except grpc.RpcError as exc:
        status = exc.code()
        if status == grpc.StatusCode.INVALID_ARGUMENT:
            http_status = 422
        elif status == grpc.StatusCode.DEADLINE_EXCEEDED:
            http_status = 504
        elif status == grpc.StatusCode.UNAVAILABLE:
            http_status = 503
        else:
            http_status = 502
        raise HTTPException(
            status_code=http_status,
            detail=f"gRPC {status.name}: {exc.details()}",
        ) from exc
