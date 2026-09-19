import asyncio
import base64
import json
from pathlib import Path

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic import TypeAdapter

from app.clients import openai_drawing_analysis as module
from app.clients.drawing_analysis import (
    DrawingAnalysisProviderError,
    DrawingAnalysisRequest,
    DrawingAnalysisTimeoutError,
)
from app.contracts.contour_extraction import load_contour_extraction_contract
from app.models.extraction import ExtractionFailure, ExtractionResult


def request():
    contract = load_contour_extraction_contract()
    return DrawingAnalysisRequest(b"drawing", "image/png", contract.prompt, contract.response_model)


def response_body(text, status="completed"):
    return {
        "id": "resp_test", "object": "response", "created_at": 0,
        "model": "gpt-6-astra", "status": status,
        "output": [{"id": "msg_test", "type": "message", "role": "assistant",
                    "status": "completed", "content": [
                        {"type": "output_text", "text": text, "annotations": []}
                    ]}],
    }


def install_transport(monkeypatch, handler):
    def factory(**kwargs):
        return AsyncOpenAI(
            **kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
    monkeypatch.setattr(module, "AsyncOpenAI", factory)


def test_real_sdk_request_and_error_result_unwrapping(monkeypatch):
    failure = {"schema_version": "2.0", "status": "error", "message": "The contour is not visible."}
    original = request()
    before = json.dumps(original.response_model.model_json_schema())

    def handler(req):
        body = json.loads(req.content)
        assert req.url.path == "/v1/responses"
        assert body["model"] == "gpt-6-astra"
        assert body["reasoning"] == {"effort": "medium"}
        assert body["store"] is False
        assert body["max_output_tokens"] == 16000
        image = body["input"][0]["content"][0]
        assert image["detail"] == "original"
        assert image["image_url"] == "data:image/png;base64," + base64.b64encode(b"drawing").decode()
        assert original.prompt in body["instructions"]
        fmt = body["text"]["format"]
        assert fmt["strict"] is True
        schema = fmt["schema"]
        assert schema["type"] == "object"
        assert "anyOf" not in schema
        assert len(schema["properties"]["result"]["anyOf"]) == 2

        def check(node):
            if isinstance(node, list):
                for item in node:
                    check(item)
            elif isinstance(node, dict):
                if "$ref" in node:
                    target = schema
                    for part in node["$ref"].split("/")[1:]:
                        target = target[part]
                if node.get("type") == "object":
                    assert node["additionalProperties"] is False
                    assert set(node["required"]) == set(node["properties"])
                if "enum" in node:
                    assert "type" in node
                for value in node.values():
                    check(value)
        check(schema)
        return httpx.Response(200, json=response_body(json.dumps({"result": failure})))

    install_transport(monkeypatch, handler)
    result = asyncio.run(module.OpenAIDrawingAnalysisClient("test-key").analyze(original))
    assert result == failure
    assert json.dumps(original.response_model.model_json_schema()) == before


@pytest.mark.parametrize("text,status", [
    ('{"result": {}}', "incomplete"),
    ("not json", "completed"),
    ('{"result": []}', "completed"),
    ('{"result": {}, "extra": 1}', "completed"),
    ('{}', "completed"),
])
def test_rejects_incomplete_or_malformed_response(monkeypatch, text, status):
    install_transport(monkeypatch, lambda req: httpx.Response(200, json=response_body(text, status)))
    with pytest.raises(DrawingAnalysisProviderError):
        asyncio.run(module.OpenAIDrawingAnalysisClient("test-key").analyze(request()))


def test_refusal_is_not_a_contour(monkeypatch):
    body = response_body("")
    body["output"][0]["content"] = [{"type": "refusal", "refusal": "Cannot comply"}]
    install_transport(monkeypatch, lambda req: httpx.Response(200, json=body))
    with pytest.raises(DrawingAnalysisProviderError, match="declined"):
        asyncio.run(module.OpenAIDrawingAnalysisClient("test-key").analyze(request()))


@pytest.mark.parametrize("timeout", [False, True])
def test_provider_errors_are_wrapped_without_retries(monkeypatch, timeout):
    calls = []

    def handler(req):
        calls.append(req)
        if timeout:
            raise httpx.ReadTimeout("private provider details", request=req)
        return httpx.Response(429, json={"error": {"message": "private provider details"}})

    install_transport(monkeypatch, handler)
    error_type = DrawingAnalysisTimeoutError if timeout else DrawingAnalysisProviderError
    with pytest.raises(error_type) as error:
        asyncio.run(module.OpenAIDrawingAnalysisClient("test-key").analyze(request()))
    assert "private" not in str(error.value)
    assert len(calls) == 1


def test_sdk_parses_full_contour_and_preserves_aliases(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    contour = json.loads((root / "extraction.example.json").read_text(encoding="utf-8"))
    install_transport(monkeypatch, lambda req: httpx.Response(
        200, json=response_body(json.dumps({"result": contour}))
    ))
    result = asyncio.run(module.OpenAIDrawingAnalysisClient("test-key").analyze(request()))
    assert result == contour
    assert "from" in result["edges"][0]
    assert "from_" not in result["edges"][0]


def test_schema_exports_match_pydantic_models():
    root = Path(__file__).resolve().parents[2]
    expected = TypeAdapter(ExtractionResult | ExtractionFailure).json_schema(by_alias=True)
    for path in [root / "extraction.schema.json", root / "app/resources/contour_extraction.schema.json"]:
        actual = json.loads(path.read_text(encoding="utf-8"))
        actual.pop("$schema")
        actual.pop("$comment")
        assert actual == expected


def test_no_output_is_not_a_contour(monkeypatch):
    body = response_body("")
    body["output"] = []
    install_transport(monkeypatch, lambda req: httpx.Response(200, json=body))
    with pytest.raises(DrawingAnalysisProviderError, match="no structured result"):
        asyncio.run(module.OpenAIDrawingAnalysisClient("test-key").analyze(request()))
