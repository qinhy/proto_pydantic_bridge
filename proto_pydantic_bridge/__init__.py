"""Pydantic v2 integration for original generated Google Protobuf message classes.

Two opt-in APIs:
* Proto[MyPbMessage] (non-invasive, preferred)
* register(MyPbMessage) (enables using MyPbMessage directly in Pydantic models)
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, TypeVar

from google.protobuf.descriptor import Descriptor, FieldDescriptor
from google.protobuf.json_format import MessageToDict, ParseDict, ParseError
from google.protobuf.message import Message
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic_core import core_schema

__all__ = ["Proto", "register", "register_many", "register_module", "validate", "dump", "proto_json_schema"]

MessageT = TypeVar("MessageT", bound=Message)


def _require_proto(cls: type[Any]) -> None:
    if not isinstance(cls, type) or not issubclass(cls, Message) or not hasattr(cls, "DESCRIPTOR"):
        raise TypeError("Expected a generated google.protobuf.message.Message class")


def validate(message_cls: type[MessageT], value: Any) -> MessageT:
    """Validate dict/instance, returning a *native* Protobuf object (never a wrapper).

    Dict inputs use Protobuf's standard ProtoJSON semantics, not Pydantic-style
    coercion or custom Field constraints. Existing instances retain identity.
    """
    _require_proto(message_cls)
    if isinstance(value, message_cls):
        return value
    if isinstance(value, dict):
        try:
            return ParseDict(value, message_cls(), ignore_unknown_fields=False)
        except (ParseError, ValueError, TypeError) as exc:
            raise ValueError(f"Invalid {message_cls.DESCRIPTOR.full_name}: {exc}") from exc
    raise ValueError(f"Expected {message_cls.__name__} instance or mapping, got {type(value).__name__}")


def dump(value: Message) -> dict[str, Any]:
    """Return a JSON-compatible dict using Protobuf's canonical JSON mapping."""
    if not isinstance(value, Message):
        raise TypeError("Expected a Protobuf message")
    return MessageToDict(value, preserving_proto_field_name=True)


class _ProtoSchema:
    """Pydantic v2 Annotated metadata adapter; does not modify pb2 classes."""

    def __get_pydantic_core_schema__(self, source_type: type[MessageT], handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        _require_proto(source_type)
        return _core_schema(source_type)

    def __get_pydantic_json_schema__(self, core: core_schema.CoreSchema, handler: GetJsonSchemaHandler) -> dict[str, Any]:
        return proto_json_schema(core["metadata"]["proto_message_cls"].DESCRIPTOR)


class Proto:
    """Use ``Proto[Detection]`` to annotate a field without monkey-patching.

    ``TypeAdapter(Proto[Detection]).validate_python({...})`` returns Detection.
    """
    def __class_getitem__(cls, message_cls: type[MessageT]):
        _require_proto(message_cls)
        return Annotated[message_cls, _ProtoSchema()]


def _core_schema(message_cls: type[MessageT]) -> core_schema.CoreSchema:
    return core_schema.no_info_plain_validator_function(
        lambda v: validate(message_cls, v),
        json_schema_input_schema=core_schema.dict_schema(core_schema.str_schema(), core_schema.any_schema()),
        serialization=core_schema.plain_serializer_function_ser_schema(
            dump,
            when_used="always",
        ),
        metadata={"proto_message_cls": message_cls},
    )


def _proto_core_schema(cls, source_type: type[MessageT], handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
    return _core_schema(cls)


def _proto_json_schema(cls, core: core_schema.CoreSchema, handler: GetJsonSchemaHandler) -> dict[str, Any]:
    return proto_json_schema(cls.DESCRIPTOR)


def _model_validate(cls, obj: Any):
    return validate(cls, obj)


def _model_dump(self):
    return dump(self)


def register(message_cls: type[MessageT], *, model_methods: bool = True) -> type[MessageT]:
    """Opt-in patch of *the actual* generated class to support direct Pydantic typing.

    Import pb2 classes normally, then register them before declaring Pydantic models.
    This is not an official Protobuf extension API: test after dependency upgrades.
    """
    _require_proto(message_cls)
    # Use descriptors explicitly so classmethod binding works on generated classes.
    setattr(message_cls, "__get_pydantic_core_schema__", classmethod(_proto_core_schema))
    setattr(message_cls, "__get_pydantic_json_schema__", classmethod(_proto_json_schema))
    if model_methods:
        setattr(message_cls, "model_validate", classmethod(_model_validate))
        setattr(message_cls, "model_dump", _model_dump)
    return message_cls


def register_many(*message_classes: type[MessageT], model_methods: bool = True) -> tuple[type[MessageT], ...]:
    """Register request, response, and other generated messages together.

    For example::

        register_many(Detection, DetectionResponse)

    Nested protobuf fields are always native messages. Register their types as
    well if you want to call .model_validate()/.model_dump() directly on them.
    """
    return tuple(register(cls, model_methods=model_methods) for cls in message_classes)


def register_module(module: Any, *, model_methods: bool = True) -> list[type[Message]]:
    """Register top-level generated messages in a single imported *_pb2 module."""
    registered: list[type[Message]] = []
    for name, cls in vars(module).items():
        if isinstance(cls, type) and issubclass(cls, Message) and getattr(cls, "__module__", None) == module.__name__:
            register(cls, model_methods=model_methods)
            registered.append(cls)
    return registered


# JSON Schema generation for common ProtoJSON field types.
# Inline nested objects rather than creating $defs, because Pydantic internally
# manages its own definitions and cannot resolve arbitrary injected $refs.
_INT = {FieldDescriptor.TYPE_INT32, FieldDescriptor.TYPE_SINT32, FieldDescriptor.TYPE_SFIXED32,
        FieldDescriptor.TYPE_UINT32, FieldDescriptor.TYPE_FIXED32}
_LONG = {FieldDescriptor.TYPE_INT64, FieldDescriptor.TYPE_SINT64, FieldDescriptor.TYPE_SFIXED64,
         FieldDescriptor.TYPE_UINT64, FieldDescriptor.TYPE_FIXED64}
_FLOAT = {FieldDescriptor.TYPE_FLOAT, FieldDescriptor.TYPE_DOUBLE}


def _value_schema(field: FieldDescriptor, ancestors: frozenset[str]) -> dict[str, Any]:
    kind = field.type
    if kind in _INT:
        return {"type": "integer"}
    if kind in _LONG:
        return {"anyOf": [{"type": "string", "pattern": "^-?[0-9]+$"}, {"type": "integer"}]}
    if kind in _FLOAT:
        return {"anyOf": [{"type": "number"}, {"type": "string", "enum": ["NaN", "Infinity", "-Infinity"]}]}
    if kind == FieldDescriptor.TYPE_BOOL:
        return {"type": "boolean"}
    if kind == FieldDescriptor.TYPE_STRING:
        return {"type": "string"}
    if kind == FieldDescriptor.TYPE_BYTES:
        return {"type": "string", "contentEncoding": "base64"}
    if kind == FieldDescriptor.TYPE_ENUM:
        return {"anyOf": [{"type": "string", "enum": [v.name for v in field.enum_type.values]}, {"type": "integer"}]}
    if kind in (FieldDescriptor.TYPE_MESSAGE, FieldDescriptor.TYPE_GROUP):
        desc = field.message_type
        if desc.full_name == "google.protobuf.Timestamp":
            return {"type": "string", "format": "date-time"}
        if desc.full_name == "google.protobuf.Duration":
            return {"type": "string", "pattern": r"^-?[0-9]+(\.[0-9]+)?s$"}
        if desc.full_name in ("google.protobuf.Struct", "google.protobuf.Value", "google.protobuf.Any"):
            return {}  # Specialized canonical ProtoJSON; left unconstrained for MVP
        if desc.full_name == "google.protobuf.ListValue":
            return {"type": "array", "items": {}}
        if desc.full_name in ("google.protobuf.StringValue", "google.protobuf.BytesValue",
                              "google.protobuf.Int32Value", "google.protobuf.UInt32Value",
                              "google.protobuf.Int64Value", "google.protobuf.UInt64Value",
                              "google.protobuf.BoolValue", "google.protobuf.DoubleValue",
                              "google.protobuf.FloatValue"):
            return {"anyOf": [_value_schema(desc.fields_by_name["value"], ancestors), {"type": "null"}]}
        return _descriptor_schema(desc, ancestors)
    return {}


def _descriptor_schema(desc: Descriptor, ancestors: frozenset[str]) -> dict[str, Any]:
    if desc.full_name in ancestors:
        # Conservative partial schema: correct type but nested recursion is not expanded.
        return {"type": "object", "x-protobuf-recursive": desc.full_name}
    ancestors = ancestors | {desc.full_name}
    props: dict[str, Any] = {}
    required = []
    for field in desc.fields:
        if field.message_type is not None and field.message_type.GetOptions().map_entry:
            value_field = field.message_type.fields_by_name["value"]
            shape = {"type": "object", "additionalProperties": _value_schema(value_field, ancestors)}
        elif field.is_repeated:
            shape = {"type": "array", "items": _value_schema(field, ancestors)}
        else:
            shape = _value_schema(field, ancestors)
        props[field.name] = shape
        if field.is_required:
            required.append(field.name)
    schema: dict[str, Any] = {"type": "object", "title": desc.name, "properties": props, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


def proto_json_schema(descriptor: Descriptor) -> dict[str, Any]:
    """JSON schema for canonical ProtoJSON for common field types.

    A documentation aid, not a full Protobuf JSON conformance schema. Recursion
    and advanced well-known types intentionally expose partial schemas.
    """
    return _descriptor_schema(descriptor, frozenset())
