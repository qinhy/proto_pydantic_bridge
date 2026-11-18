"""Native gRPC detection server.

Run: python examples/detection/server/grpc_server.py --host 127.0.0.1 --port 50051
"""
from __future__ import annotations

import argparse
from concurrent import futures
import logging
from pathlib import Path
import sys

import grpc

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from protocol.detection_pb2 import Detection, DetectionResponse
from protocol.detection_pb2_grpc import (
    DetectionServiceServicer,
    add_DetectionServiceServicer_to_server,
)
from algorithm.processing import InvalidDetection, process_detection

log = logging.getLogger(__name__)


class DetectionService(DetectionServiceServicer):
    def Detect(self, request: Detection, context: grpc.ServicerContext) -> DetectionResponse:
        try:
            result = process_detection(request, processed_by="grpc")
        except InvalidDetection as exc:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        log.info("gRPC detected class_id=%d image_id=%r", request.class_id, request.image_id)
        return result


def start_server(host: str = "127.0.0.1", port: int = 50051, *, workers: int = 4):
    """Start a server and return (server, bound_port); port=0 picks a free port."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=workers))
    add_DetectionServiceServicer_to_server(DetectionService(), server)
    bound_port = server.add_insecure_port(f"{host}:{port}")
    if bound_port == 0:
        raise RuntimeError(f"Failed to bind gRPC on {host}:{port}")
    server.start()
    return server, bound_port


def main() -> None:
    parser = argparse.ArgumentParser(description="Native protobuf gRPC demo server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=50051)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    server, bound_port = start_server(args.host, args.port, workers=args.workers)
    log.info("gRPC listening on %s:%d", args.host, bound_port)
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        log.info("Shutting down gRPC")
        server.stop(grace=2).wait(timeout=5)


if __name__ == "__main__":
    main()
