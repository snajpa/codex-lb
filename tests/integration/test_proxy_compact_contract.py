from __future__ import annotations

import json

import pytest
from sqlalchemy import select

import app.core.clients.proxy as proxy_client_module
import app.modules.proxy.service as proxy_module
from app.core.openai.models import CompactResponsePayload
from app.core.openai.requests import ResponsesCompactRequest
from app.db.models import RequestLog
from app.db.session import SessionLocal
from tests.integration.compact_test_helpers import _make_auth_json

pytestmark = pytest.mark.integration


def test_compact_v2_preserves_reasoning_tools_and_full_input():
    tools = [{"type": "function", "name": "read", "parameters": {"type": "object"}, "future": "kept"}]
    history = [{"role": "user", "content": "complete-history-" + "x" * 430_000}]
    request = ResponsesCompactRequest.model_validate(
        {
            "model": "gpt-5.1",
            "input": history,
            "instructions": "policy",
            "reasoning": {"effort": "high"},
            "tools": tools,
            "tool_choice": "auto",
            "parallel_tool_calls": True,
            "prompt_cache_key": "stable",
        }
    )
    wire = proxy_client_module._responses_compact_payload_for_responses_endpoint(request)
    assert wire.get("tools") == tools
    assert wire["reasoning"] == {"effort": "high"}
    assert wire["input"] == [*history, {"type": "compaction_trigger"}]
    assert wire["prompt_cache_key"] == "stable"
    assert wire["parallel_tool_calls"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/v1/responses/compact", "/backend-api/codex/responses/compact"])
async def test_compact_endpoint_records_session_kind_and_uses_remaining_deadline(async_client, monkeypatch, path):
    auth = _make_auth_json("compact-contract", "compact-contract@example.com")
    imported = await async_client.post(
        "/api/accounts/import", files={"auth_json": ("auth.json", json.dumps(auth), "application/json")}
    )
    assert imported.status_code == 200
    seen_budgets: list[float | None] = []

    async def compact(payload, headers, access_token, account_id):
        seen_budgets.append(proxy_client_module._effective_compact_total_timeout())
        return CompactResponsePayload.model_validate(
            {
                "object": "response.compaction",
                "output": [
                    {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "retained"}]},
                    {"type": "compaction", "encrypted_content": "opaque"},
                ],
                "usage": {
                    "input_tokens": 1024,
                    "output_tokens": 12,
                    "total_tokens": 1036,
                    "input_tokens_details": {"cached_tokens": 768},
                },
            }
        )

    monkeypatch.setattr(proxy_module, "core_compact_responses", compact)
    response = await async_client.post(
        path,
        headers={"session_id": "compact-contract-session"},
        json={
            "model": "gpt-5.1",
            "instructions": "policy",
            "input": [{"role": "user", "content": "history"}],
            "reasoning": {"effort": "high"},
            "prompt_cache_key": "compact-contract-key",
        },
    )
    assert response.status_code == 200
    assert response.json()["output"] == [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "retained"}]},
        {"type": "compaction", "encrypted_content": "opaque"},
    ]
    assert len(seen_budgets) == 1
    from app.core.config.settings import get_settings

    assert seen_budgets[0] is not None
    budget = get_settings().compact_request_budget_seconds
    assert budget - 5 < seen_budgets[0] <= budget
    async with SessionLocal() as session:
        row = (await session.execute(select(RequestLog).where(RequestLog.model == "gpt-5.1"))).scalar_one()
        assert row.request_kind == "compaction"
        assert row.session_id == "compact-contract-session"
        assert row.reasoning_effort == "high"
        assert row.cached_input_tokens == 768


@pytest.mark.parametrize("object_kind", ["response", "response.compaction"])
def test_native_compaction_does_not_relabel_plain_text_as_encrypted_state(object_kind):
    from app.core.clients.proxy import ProxyResponseError

    reply = {
        "object": object_kind,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "ordinary plaintext summary"}],
            }
        ],
    }
    with pytest.raises(ProxyResponseError) as error:
        proxy_client_module._normalize_compact_response_payload_shape(reply)
    assert error.value.status_code == 502
    assert "encrypted" in str(error.value.payload).lower()


def test_native_compaction_keeps_the_supplied_context_window():
    user = {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "retained"}]}
    capsule = {"type": "compaction", "encrypted_content": "opaque", "id": "cmp_native"}
    reply = {"object": "response", "output": [user, capsule], "usage": {"input_tokens": 17}}
    normalized = proxy_client_module._normalize_compact_response_payload_shape(reply)
    assert normalized["object"] == "response.compaction"
    assert normalized["output"] == [user, capsule]
    assert normalized["usage"] == reply["usage"]


@pytest.mark.parametrize(
    "extra",
    [
        {"type": "compaction", "encrypted_content": ""},
        {"type": "compaction", "encrypted_content": "second"},
        {"type": "compaction", "encrypted_content": None},
    ],
)
def test_native_compaction_rejects_additional_or_invalid_capsules(extra):
    from app.core.clients.proxy import ProxyResponseError

    reply = {"object": "response.compaction", "output": [{"type": "compaction", "encrypted_content": "opaque"}, extra]}
    with pytest.raises(ProxyResponseError):
        proxy_client_module._normalize_compact_response_payload_shape(reply)


@pytest.mark.parametrize(
    "source_kind,expected",
    [
        ("subscription", "responses_v2"),
        ("openai_compatible", None),
    ],
)
def test_model_advertises_only_its_supported_native_compaction_protocol(source_kind, expected):
    from dataclasses import replace

    from app.modules.proxy.api import _to_model_metadata
    from tests.integration.test_v1_models import _make_upstream_model

    model = replace(_make_upstream_model("test-native-capability"), source_kind=source_kind)
    metadata = _to_model_metadata(model, context_window=model.context_window)
    assert metadata.native_compaction_protocol == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("contract", ["prefix", "window", "omitted_tools", "empty_tools"])
async def test_compaction_trigger_stream_preserves_returned_native_window(async_client, monkeypatch, contract):
    import app.modules.proxy.service as service_module
    from app.core.openai.models import CompactResponsePayload
    from tests.integration.compact_test_helpers import _make_auth_json

    auth = _make_auth_json("native-window", "native-window@example.com")
    imported = await async_client.post(
        "/api/accounts/import", files={"auth_json": ("auth.json", json.dumps(auth), "application/json")}
    )
    assert imported.status_code == 200
    output = [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "retained"}]},
        {"type": "compaction", "id": "cmp_native", "status": "completed", "encrypted_content": "opaque"},
    ]

    if contract != "window":
        output = output[1:]
    tools = [{"type": "function", "name": "read_file", "parameters": {"type": "object"}}]
    seen = []

    async def compact(payload, *_args, **_kwargs):
        seen.append(payload.to_payload())
        return CompactResponsePayload.model_validate({"object": "response.compaction", "output": output})

    monkeypatch.setattr(service_module, "core_compact_responses", compact)
    request = {
        "model": "gpt-5.4",
        "stream": True,
        "instructions": "policy",
        "reasoning": {"effort": "high"},
        "parallel_tool_calls": False,
        "input": [{"role": "user", "content": "history"}, {"type": "compaction_trigger"}],
    }
    if contract != "omitted_tools":
        request["tools"] = [] if contract == "empty_tools" else tools
    response = await async_client.post("/backend-api/codex/responses", json=request)
    assert response.status_code == 200, response.text
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line[6:] != "[DONE]"
    ]
    terminal = [event for event in events if event["type"] == "response.completed"]
    assert len(terminal) == 1 and terminal[0]["response"]["output"] == output
    assert len(seen) == 1
    if contract == "omitted_tools":
        assert "tools" not in seen[0], "native projection manufactured a tools declaration"
    else:
        assert seen[0]["tools"] == ([] if contract == "empty_tools" else tools)
    assert seen[0]["reasoning"] == {"effort": "high"} and seen[0]["parallel_tool_calls"] is False
    added = [event for event in events if event["type"] == "response.output_item.added"]
    done = [event for event in events if event["type"] == "response.output_item.done"]
    assert [event["output_index"] for event in added] == list(range(len(output)))
    assert [event["output_index"] for event in done] == list(range(len(output)))
    assert [event["item"] for event in done] == output
    # Indexed consumers append added items and address that slot for done events.
    snapshot = []
    for event in events:
        if event["type"] == "response.output_item.added":
            assert event["output_index"] == len(snapshot)
            snapshot.append(event["item"])
        elif event["type"] == "response.output_item.done":
            snapshot[event["output_index"]] = event["item"]
    assert snapshot == output
    assert [event["sequence_number"] for event in events] == list(range(len(events)))
