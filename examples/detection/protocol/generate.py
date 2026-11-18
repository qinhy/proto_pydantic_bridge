"""Regenerate native *_pb2.py, *.pyi, and *_pb2_grpc.py in this directory.

Install once: python -m pip install grpcio-tools
Run from the repository root: python examples/detection/protocol/generate.py
"""
from __future__ import annotations

from pathlib import Path
import re

PROTO_NAME = "detection" # detection.proto

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
        str(directory / f"{PROTO_NAME}.proto"),
    ]
    if protoc.main(args) != 0:
        raise SystemExit("protoc generation failed")

    # Keep protocol/ self-contained as a package without requiring protocol/ on sys.path.
    grpc_file = directory / f"{PROTO_NAME}_pb2_grpc.py"
    text = grpc_file.read_text(encoding="utf-8")
    updated = text.replace(
        f"import {PROTO_NAME}_pb2 as {PROTO_NAME}__pb2",
        f"from . import {PROTO_NAME}_pb2 as {PROTO_NAME}__pb2",
    )
    if updated != text:
        grpc_file.write_text(updated, encoding="utf-8")

    # bridge models
    grpc_file = directory / f"{PROTO_NAME}_pb2.py"
    text = grpc_file.read_text(encoding="utf-8")
    # Find all Protobuf message classes
    classes = re.findall(
        r"^class\s+(\w+)\(_message\.Message\):",
        (directory / f"{PROTO_NAME}_pb2.pyi").read_text(encoding="utf-8"), re.MULTILINE,
    )
    # Generate registration code
    registration = (
        "from proto_pydantic_bridge import register_many\n"
        f"register_many({', '.join(classes)})\n"
    )
    updated = text
    if classes and registration.strip() not in text:
        updated = text.rstrip() + "\n\n" + registration
    if updated != text:
        grpc_file.write_text(updated, encoding="utf-8")

    print("Generated protocol/{PROTO_NAME}_pb2.py, protocol/{PROTO_NAME}_pb2.pyi, and protocol/{PROTO_NAME}_pb2_grpc.py")


if __name__ == "__main__":
    main()
