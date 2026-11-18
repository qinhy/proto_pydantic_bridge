"""CLI for the native gRPC server (and optional FastAPI HTTP endpoint).

Examples:
  python examples/detection/grpc_client.py --class-id 3 --confidence 0.95
  python examples/detection/grpc_client.py --transport http --backend grpc
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib import error, request as urllib_request
from urllib.parse import urlencode

import grpc

from bridge_models import Detection, DetectionResponse
from detection_pb2_grpc import DetectionServiceStub


def call_grpc(message: Detection, *, target: str = "127.0.0.1:50051", timeout: float = 3) -> DetectionResponse:
    with grpc.insecure_channel(target) as channel:
        response = DetectionServiceStub(channel).Detect(message, timeout=timeout)
    assert type(response) is DetectionResponse
    return response


def call_http(
    message: Detection,
    *,
    url: str = "http://127.0.0.1:8000/detect",
    backend: str = "local",
    timeout: float = 3,
) -> DetectionResponse:
    full_url = f"{url}{'&' if '?' in url else '?'}{urlencode({'backend': backend})}"
    body = json.dumps(message.model_dump()).encode("utf-8")
    req = urllib_request.Request(
        full_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(req, timeout=timeout) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    return DetectionResponse.model_validate(parsed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Send Detection to gRPC or FastAPI")
    parser.add_argument("--transport", choices=("grpc", "http"), default="grpc")
    parser.add_argument("--target", default="127.0.0.1:50051", help="gRPC address")
    parser.add_argument("--url", default="http://127.0.0.1:8000/detect")
    parser.add_argument("--backend", choices=("local", "grpc"), default="local", help="FastAPI backend")
    parser.add_argument("--class-id", type=int, default=1)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--bbox", nargs=4, type=float, metavar=("X1", "Y1", "X2", "Y2"), default=[10, 20, 100, 200])
    parser.add_argument("--image-id", default="camera-001")
    parser.add_argument("--timeout", type=float, default=3)
    args = parser.parse_args()

    # Native protobuf instance produced by the bridge's Pydantic-style API.
    message = Detection.model_validate({
        "class_id": args.class_id,
        "confidence": args.confidence,
        "bbox": args.bbox,
        "image_id": args.image_id,
    })
    assert type(message) is Detection
    try:
        if args.transport == "grpc":
            result = call_grpc(message, target=args.target, timeout=args.timeout)
        else:
            result = call_http(message, url=args.url, backend=args.backend, timeout=args.timeout)
    except (grpc.RpcError, error.URLError, TimeoutError, ValueError) as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result.model_dump(), indent=2))
    print(f"native_type={type(result).__name__}; protobuf_bytes={len(result.SerializeToString())}")


if __name__ == "__main__":
    main()
