"""Gemini tool parameter schemas (#12).

Kind: baseline regression. On the parent commit ``_convert_tools`` forwards the
OpenAI-style parameter schema unchanged. google-genai 3.3.0 then either sends
``additional_properties`` (which the API answers with a 400) or raises a pydantic
``ValidationError`` client-side for keywords it has no field for (``$schema``,
``oneOf``, ``const``, ``examples``, ``exclusiveMinimum``, ``$ref``/``$defs`` and
type lists).

The requests are built by the real google-genai request path over an httpx2
``MockTransport``; no request leaves the process (environment: local-faked).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx2
import pytest
from google import genai
from google.genai import types

from ayder_cli.providers.impl.gemini import GeminiProvider
from ayder_cli.tools.definition import TOOL_DEFINITIONS

_OK = {"candidates": [{"content": {"role": "model", "parts": [{"text": "ok"}]}}]}


def _client(captured: list[dict[str, Any]]) -> genai.Client:
    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(json.loads(request.content))
        return httpx2.Response(200, json=_OK)

    return genai.Client(
        api_key="x",
        http_options=types.HttpOptions(
            base_url="http://mock.local",
            httpx_async_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
        ),
    )


def _tool(name: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": name, "description": "d", "parameters": parameters},
    }


def _builtin(name: str) -> dict[str, Any]:
    (definition,) = [td for td in TOOL_DEFINITIONS if td.name == name]
    return definition.to_openai_schema()


def _send(tools: list[dict[str, Any]]) -> dict[str, Any]:
    """Send ``tools`` through the real SDK request path; return the captured body."""
    captured: list[dict[str, Any]] = []
    client = _client(captured)
    config = types.GenerateContentConfig(tools=GeminiProvider._convert_tools(tools))

    async def go() -> None:
        await client.aio.models.generate_content(model="m", contents="hi", config=config)

    asyncio.run(go())
    return captured[-1]


def _declaration(body: dict[str, Any]) -> dict[str, Any]:
    return body["tools"][0]["functionDeclarations"][0]


# --- the shipped tools reach the wire ---------------------------------------------


@pytest.mark.parametrize("tool_name", ["bash", "fetch_web"])
def test_builtin_tools_reach_the_wire_without_additional_properties(tool_name):
    """Baseline regression: the wire carries ``additional_properties`` today."""
    body = _send([_builtin(tool_name)])

    assert "additional_properties" not in json.dumps(body)
    assert "additionalProperties" not in json.dumps(body)


def test_bash_environment_stays_an_object_with_its_description():
    """Preservation: stripping the keyword keeps the property itself."""
    source = _builtin("bash")["function"]["parameters"]["properties"]["environment"]
    body = _send([_builtin("bash")])

    environment = _declaration(body)["parameters"]["properties"]["environment"]
    assert environment["type"] == "OBJECT"
    assert environment["description"] == source["description"]


# --- keywords the SDK has no field for ---------------------------------------------

_KEYWORD_SCHEMAS = {
    "$schema": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"a": {"type": "string"}},
    },
    "oneOf": {
        "type": "object",
        "properties": {"a": {"oneOf": [{"type": "string"}, {"type": "integer"}]}},
    },
    "const": {"type": "object", "properties": {"a": {"type": "string", "const": "x"}}},
    "examples": {"type": "object", "properties": {"a": {"type": "string", "examples": ["x"]}}},
    "exclusiveMinimum": {
        "type": "object",
        "properties": {"a": {"type": "integer", "exclusiveMinimum": 0}},
    },
    "$ref": {
        "type": "object",
        "properties": {"a": {"$ref": "#/$defs/A"}},
        "$defs": {"A": {"type": "string"}},
    },
    "type list": {
        "type": "object",
        "properties": {"a": {"type": ["string", "null"]}},
    },
    "additionalProperties false": {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "additionalProperties": False,
    },
}


@pytest.mark.parametrize("schema", list(_KEYWORD_SCHEMAS.values()), ids=list(_KEYWORD_SCHEMAS))
def test_a_schema_with_json_schema_keywords_builds_a_valid_sdk_config(schema):
    """Baseline regression: every case but the last raises ValidationError today."""
    tools = GeminiProvider._convert_tools([_tool("t", schema)])

    types.GenerateContentConfig(tools=tools)  # raises pydantic.ValidationError on main


# --- what the allowlist keeps and rewrites -----------------------------------------


def _sent_parameters(schema: dict[str, Any]) -> dict[str, Any]:
    return _declaration(_send([_tool("t", schema)]))["parameters"]


def test_property_names_that_collide_with_keywords_survive():
    """Baseline regression: a property called ``title`` must not be treated as a keyword."""
    sent = _sent_parameters(
        {
            "type": "object",
            "properties": {
                "title": {"type": "string", "title": "Title"},
                "const": {"type": "string", "const": "x"},
                "default": {"type": "string", "default": "d"},
            },
            "required": ["title"],
        }
    )

    assert sorted(sent["properties"]) == ["const", "default", "title"]
    assert sent["required"] == ["title"]
    assert sent["properties"]["title"]["title"] == "Title"
    assert sent["properties"]["default"]["default"] == "d"
    assert "const" not in sent["properties"]["const"]


def test_a_type_list_with_null_becomes_the_type_plus_nullable():
    sent = _sent_parameters(
        {"type": "object", "properties": {"a": {"type": ["string", "null"]}}}
    )

    assert sent["properties"]["a"] == {"type": "STRING", "nullable": True}


def test_oneof_is_sent_as_anyof():
    sent = _sent_parameters(
        {
            "type": "object",
            "properties": {"a": {"oneOf": [{"type": "string"}, {"type": "integer"}]}},
        }
    )

    # The SDK serialises snake_case keys; the API accepts both spellings.
    assert sent["properties"]["a"]["any_of"] == [{"type": "STRING"}, {"type": "INTEGER"}]


def test_supported_keywords_are_kept():
    """Preservation: what Gemini accepts passes through unchanged."""
    sent = _sent_parameters(
        {
            "type": "object",
            "description": "top",
            "properties": {
                "mode": {"type": "string", "enum": ["a", "b"], "description": "which"},
                "code": {"type": "string", "pattern": "^[a-z]+$"},
                "n": {"type": "integer", "minimum": 1, "maximum": 9},
                "tags": {
                    "type": "array",
                    "items": {"type": "string", "pattern": "^x"},
                    "minItems": 1,
                },
            },
            "required": ["mode"],
        }
    )

    assert sent["description"] == "top"
    assert sent["required"] == ["mode"]
    mode = sent["properties"]["mode"]
    assert mode["enum"] == ["a", "b"] and mode["description"] == "which"
    assert sent["properties"]["code"]["pattern"] == "^[a-z]+$"
    n = sent["properties"]["n"]
    assert n["minimum"] == 1 and n["maximum"] == 9
    tags = sent["properties"]["tags"]
    assert tags["items"]["pattern"] == "^x"
    assert tags["min_items"] == 1  # the SDK serialises snake_case keys


def test_nested_unsupported_keywords_are_dropped_at_every_level():
    sent = _sent_parameters(
        {
            "type": "object",
            "properties": {
                "opt": {
                    "anyOf": [
                        {"type": "string", "additionalProperties": False},
                        {"type": "null"},
                    ]
                },
                "rows": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "properties": {"k": {"type": "string", "examples": ["v"]}},
                    },
                },
            },
        }
    )

    assert "additional_properties" not in json.dumps(sent)
    assert sent["properties"]["rows"]["items"]["properties"]["k"] == {"type": "STRING"}


def test_a_tool_without_parameters_still_gets_an_empty_object():
    declaration = GeminiProvider._convert_tools(
        [{"type": "function", "function": {"name": "t", "description": "d"}}]
    )[0]["function_declarations"][0]

    assert declaration["parameters"] == {"type": "object", "properties": {}}
