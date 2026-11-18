from concurrent import futures

import grpc
import pytest
from fastapi import FastAPI, Body
from fastapi.testclient import TestClient
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message import Message
from google.protobuf import type_pb2
from pydantic import BaseModel, TypeAdapter, ValidationError

from proto_pydantic_bridge import Proto, dump, register, register_many, register_module, validate


def make_types():
    fd = descriptor_pb2.FileDescriptorProto()
    fd.name = "bridge_compatibility_test.proto"
    fd.package = "bridge.demo"
    fd.syntax = "proto3"

    detection = fd.message_type.add()
    detection.name = "Detection"
    for name, number, kind in [
        ("class_id", 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32),
        ("confidence", 2, descriptor_pb2.FieldDescriptorProto.TYPE_FLOAT),
        ("payload", 3, descriptor_pb2.FieldDescriptorProto.TYPE_BYTES),
        ("sequence", 4, descriptor_pb2.FieldDescriptorProto.TYPE_UINT64),
    ]:
        field = detection.field.add()
        field.name, field.number, field.type = name, number, kind
        field.label = descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL

    scene = fd.message_type.add()
    scene.name = "Scene"
    field = scene.field.add()
    field.name, field.number = "detections", 1
    field.label = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED
    field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
    field.type_name = ".bridge.demo.Detection"

    label_map = scene.nested_type.add()
    label_map.name = "LabelsEntry"
    label_map.options.map_entry = True
    key = label_map.field.add()
    key.name, key.number, key.label, key.type = "key", 1, 1, descriptor_pb2.FieldDescriptorProto.TYPE_STRING
    value = label_map.field.add()
    value.name, value.number, value.label, value.type = "value", 2, 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32
    map_field = scene.field.add()
    map_field.name, map_field.number, map_field.label, map_field.type = "labels", 2, 3, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
    map_field.type_name = ".bridge.demo.Scene.LabelsEntry"

    pool = descriptor_pool.DescriptorPool()
    pool.Add(fd)
    return (
        message_factory.GetMessageClass(pool.FindMessageTypeByName("bridge.demo.Detection")),
        message_factory.GetMessageClass(pool.FindMessageTypeByName("bridge.demo.Scene")),
    )


Detection, Scene = make_types()


def test_annotated_type_preserves_native_protobuf_and_wire_bytes():
    adapter = TypeAdapter(Proto[Detection])
    obj = adapter.validate_python({"class_id": 4, "confidence": 0.9, "payload": "AQID", "sequence": "123456789"})
    assert type(obj) is Detection
    assert obj.payload == b"\x01\x02\x03"
    assert obj.sequence == 123456789
    assert Detection.FromString(obj.SerializeToString()) == obj
    assert adapter.validate_python(obj) is obj
    assert adapter.dump_python(obj)["payload"] == "AQID"
    assert adapter.dump_python(obj)["sequence"] == "123456789"
    assert adapter.json_schema()["properties"]["class_id"]["type"] == "integer"


def test_direct_registration_and_nested_model():
    register(Detection)

    class Envelope(BaseModel):
        message: Detection

    envelope = Envelope.model_validate({"message": {"class_id": 3, "confidence": 0.5}})
    assert type(envelope.message) is Detection
    assert envelope.message.SerializeToString()
    assert envelope.model_dump() == {"message": {"class_id": 3, "confidence": 0.5}}
    assert Detection.model_validate({"class_id": 8}).class_id == 8
    assert envelope.message.model_dump()["class_id"] == 3
    assert Envelope.model_json_schema()["properties"]["message"]["type"] == "object"


def test_nested_and_map_schema():
    register(Scene)
    obj = TypeAdapter(Scene).validate_python({
        "detections": [{"class_id": 1}, {"class_id": 2}],
        "labels": {"person": 3}
    })
    assert type(obj) is Scene
    assert [d.class_id for d in obj.detections] == [1, 2]
    assert obj.labels["person"] == 3
    restored = Scene.FromString(obj.SerializeToString())
    assert restored == obj
    schema = TypeAdapter(Scene).json_schema()
    assert schema["properties"]["detections"]["type"] == "array"
    assert schema["properties"]["labels"]["additionalProperties"]["type"] == "integer"


def test_invalid_input_raises_pydantic_error():
    adapter = TypeAdapter(Proto[Detection])
    with pytest.raises(ValidationError):
        adapter.validate_python({"missing_field": True})
    with pytest.raises(ValidationError):
        adapter.validate_python("wrong")


def test_registered_works_with_fastapi_docs():
    register(Detection)
    app = FastAPI()

    @app.post("/detect", response_model=Detection)
    def detect(body: Detection = Body(...)):
        assert isinstance(body, Detection)
        return body

    client = TestClient(app)
    schema = client.get("/openapi.json")
    assert schema.status_code == 200, schema.text
    assert "/detect" in schema.json()["paths"]
    response = client.post("/detect", json={"class_id": 7, "confidence": 0.75})
    assert response.status_code == 200, response.text
    assert response.json()["class_id"] == 7


def test_standard_grpc_serializer_accepts_adapted_instance():
    register(Detection)
    obj = Detection.model_validate({"class_id": 42, "confidence": 0.75})
    assert isinstance(obj, Message)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(
        "bridge.demo.Echo",
        {"Echo": grpc.unary_unary_rpc_method_handler(
            lambda request, context: request,
            request_deserializer=Detection.FromString,
            response_serializer=Detection.SerializeToString,
        )},
    ),))
    port = server.add_insecure_port("127.0.0.1:0")
    server.start()
    try:
        with grpc.insecure_channel(f"127.0.0.1:{port}") as channel:
            rpc = channel.unary_unary(
                "/bridge.demo.Echo/Echo",
                request_serializer=Detection.SerializeToString,
                response_deserializer=Detection.FromString,
            )
            response = rpc(obj, timeout=3)
        assert type(response) is Detection
        assert response == obj
    finally:
        server.stop(grace=0).wait(timeout=5)


def test_bulk_registration_for_regular_pb2_module():
    regs = register_module(type_pb2)
    assert type_pb2.Type in regs
    assert type_pb2.Field in regs
    assert type_pb2.Type.model_validate({"name": "demo.Type"}).name == "demo.Type"


def test_non_invasive_annotation_inside_pydantic_model():
    class Request(BaseModel):
        detection: Proto[Detection]

    req = Request.model_validate({"detection": {"class_id": 15}})
    assert type(req.detection) is Detection
    assert req.model_dump() == {"detection": {"class_id": 15}}
    assert Request.model_json_schema()["properties"]["detection"]["type"] == "object"


def test_existing_pb2_instance_preserves_identity():
    msg = Detection(class_id=99)
    assert validate(Detection, msg) is msg
    assert dump(msg) == {"class_id": 99}


def test_both_request_and_response_pydantic_and_native_grpc():
    # Build two message classes with the same descriptors/metaclass as _pb2 code.
    from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

    proto = descriptor_pb2.FileDescriptorProto()
    proto.name = 'request_response_test.proto'
    proto.package = 'bridge.integration'
    proto.syntax = 'proto3'
    det = proto.message_type.add()
    det.name = 'Detection'
    f = det.field.add()
    f.name, f.number, f.type = 'class_id', 1, descriptor_pb2.FieldDescriptorProto.TYPE_INT32
    f = det.field.add()
    f.name, f.number, f.type = 'confidence', 2, descriptor_pb2.FieldDescriptorProto.TYPE_FLOAT
    response_desc = proto.message_type.add()
    response_desc.name = 'DetectionResponse'
    f = response_desc.field.add()
    f.name, f.number, f.type = 'detections', 1, descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
    f.label = descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED
    f.type_name = '.bridge.integration.Detection'
    f = response_desc.field.add()
    f.name, f.number, f.type = 'total', 2, descriptor_pb2.FieldDescriptorProto.TYPE_INT32
    pool = descriptor_pool.DescriptorPool()
    pool.Add(proto)
    Det = message_factory.GetMessageClass(pool.FindMessageTypeByName('bridge.integration.Detection'))
    Resp = message_factory.GetMessageClass(pool.FindMessageTypeByName('bridge.integration.DetectionResponse'))

    assert register_many(Det, Resp) == (Det, Resp)
    det_obj = Det.model_validate({'class_id': 8, 'confidence': 0.5})
    resp_obj = Resp.model_validate({'detections': [{'class_id': 8, 'confidence': 0.5}], 'total': 1})
    assert type(resp_obj) is Resp
    assert type(resp_obj.detections[0]) is Det
    assert resp_obj.detections[0].model_dump() == {'class_id': 8, 'confidence': 0.5}
    assert resp_obj.model_dump() == {'detections': [{'class_id': 8, 'confidence': 0.5}], 'total': 1}

    class Exchange(BaseModel):
        request: Det
        response: Resp

    exchange = Exchange.model_validate({'request': {'class_id': 8}, 'response': resp_obj})
    assert type(exchange.request) is Det
    assert type(exchange.response) is Resp
    assert Exchange.model_json_schema()['properties']['response']['properties']['detections']['type'] == 'array'

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
    server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(
        'bridge.integration.Service',
        {'Detect': grpc.unary_unary_rpc_method_handler(
            lambda request, _: Resp(detections=[request], total=1),
            request_deserializer=Det.FromString,
            response_serializer=Resp.SerializeToString,
        )},
    ),))
    port = server.add_insecure_port('127.0.0.1:0')
    server.start()
    try:
        with grpc.insecure_channel(f'127.0.0.1:{port}') as channel:
            call = channel.unary_unary(
                '/bridge.integration.Service/Detect',
                request_serializer=Det.SerializeToString,
                response_deserializer=Resp.FromString,
            )
            rpc_resp = call(det_obj, timeout=3)
        assert type(rpc_resp) is Resp
        assert type(rpc_resp.detections[0]) is Det
        assert rpc_resp.total == 1
        # Pydantic layer works with the received native Protobuf response too.
        assert Resp.model_validate(rpc_resp) is rpc_resp
        assert TypeAdapter(Resp).validate_python(rpc_resp) is rpc_resp
    finally:
        server.stop(grace=0).wait(timeout=5)

    app = FastAPI()

    @app.post('/detect', response_model=Resp)
    def detect(body: Det = Body(...)):
        return Resp(detections=[body], total=1)

    c = TestClient(app)
    assert c.get('/openapi.json').status_code == 200
    result = c.post('/detect', json={'class_id': 8, 'confidence': 0.5})
    assert result.status_code == 200, result.text
    assert result.json() == {'detections': [{'class_id': 8, 'confidence': 0.5}], 'total': 1}
