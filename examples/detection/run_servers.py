"""Run the detection example's gRPC and FastAPI servers together."""

import logging

import uvicorn

from server.fastapi_server import app
from server.grpc_server import start_server


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    grpc_server, port = start_server()
    try:
        logging.info("gRPC listening on 127.0.0.1:%d", port)
        uvicorn.run(app, host="127.0.0.1", port=8000)
    except KeyboardInterrupt:
        pass
    finally:
        grpc_server.stop(grace=2).wait(timeout=5)


if __name__ == "__main__":
    main()
