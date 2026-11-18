from google.protobuf.type_pb2 import Type
from pydantic import BaseModel, TypeAdapter
from proto_pydantic_bridge import Proto, register

# Option 1: non-invasive annotation.
adapter = TypeAdapter(Proto[Type])
obj = adapter.validate_python({"name": "example.User"})
assert type(obj) is Type
assert Type.FromString(obj.SerializeToString()) == obj
print("Annotation result:", adapter.dump_python(obj))
print("Pydantic JSON schema title:", adapter.json_schema()["title"])

# Option 2: keep original class in annotation.
register(Type)

class Envelope(BaseModel):
    message: Type

envelope = Envelope.model_validate({"message": {"name": "example.User"}})
assert type(envelope.message) is Type
print("Direct-class model:", envelope.model_dump())
print("gRPC-ready bytes:", envelope.message.SerializeToString())
