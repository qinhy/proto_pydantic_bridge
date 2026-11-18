"""Regenerate native *_pb2.py and *_pb2_grpc.py next to this script.

Install once: python -m pip install grpcio-tools
Run from the repository root: python examples/detection/generate.py
"""
from __future__ import annotations

from pathlib import Path


def main() -> None:
    try:
        from grpc_tools import protoc
    except ImportError as exc:
        raise SystemExit("Install the code generator: python -m pip install grpcio-tools") from exc

    directory = Path(__file__).resolve().parent
    args = [
        "grpc_tools.protoc",
        f"-I{directory}",
        f"--python_out={directory}",
        f"--pyi_out={directory}",
        f"--grpc_python_out={directory}",
        str(directory / "detection.proto"),
    ]
    if protoc.main(args) != 0:
        raise SystemExit("protoc generation failed")
    print("Generated detection_pb2.py, detection_pb2.pyi, and detection_pb2_grpc.py")


if __name__ == "__main__":
    main()
