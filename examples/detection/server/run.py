"""Run gRPC and FastAPI servers together."""

import logging

import uvicorn

from server.fastapi_server import app
from server.grpc_server import start_server
from protocol.detection_pb2 import DetectionServerConfig

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = DetectionServerConfig()
    grpc_server, port = start_server(host=config.host, port=config.grpc_port)
    try:
        logging.info(f"gRPC listening on {config.host}:{port}")
        uvicorn.run(app, host=config.host, port=config.fastapi_port)
    except KeyboardInterrupt:
        pass
    finally:
        grpc_server.stop(grace=2).wait(timeout=5)


if __name__ == "__main__":
    main()
