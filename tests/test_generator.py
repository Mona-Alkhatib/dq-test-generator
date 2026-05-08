import json
from unittest.mock import MagicMock

from dqgen.generator import generate_proposed_tests
from dqgen.models import ColumnProfile, TableProfile


def _profile() -> TableProfile:
    return TableProfile(
        schema="raw",
        name="orders",
        row_count=100,
        columns=[
            ColumnProfile(name="id", dtype="INTEGER", nullable=False, null_count=0, distinct_count=100),
            ColumnProfile(
                name="status",
                dtype="VARCHAR",
                nullable=False,
                null_count=0,
                distinct_count=3,
                top_values=[("placed", 60), ("shipped", 30), ("completed", 10)],
            ),
        ],
    )


def _claude_response(payload: list[dict]) -> MagicMock:
    """Build a fake Anthropic response whose content is the prefill continuation."""
    text_block = MagicMock(type="text", text=json.dumps(payload)[1:])  # drop leading '['
    response = MagicMock(content=[text_block])
    return response


def test_generate_returns_parsed_proposals():
    canned = [
        {"column": "id", "test": "not_null", "args": {}, "rationale": "PK, no nulls"},
        {"column": "id", "test": "unique", "args": {}, "rationale": "100 distinct of 100 rows"},
        {
            "column": "status",
            "test": "accepted_values",
            "args": {"values": ["placed", "shipped", "completed"]},
            "rationale": "3 stable values",
        },
    ]
    client = MagicMock()
    client.messages.create.return_value = _claude_response(canned)

    out = generate_proposed_tests(_profile(), client=client)

    assert [p.column for p in out] == ["id", "id", "status"]
    assert out[2].args["values"] == ["placed", "shipped", "completed"]


def test_generate_uses_assistant_prefill():
    client = MagicMock()
    client.messages.create.return_value = _claude_response([])

    generate_proposed_tests(_profile(), client=client)

    kwargs = client.messages.create.call_args.kwargs
    last_message = kwargs["messages"][-1]
    assert last_message["role"] == "assistant"
    assert last_message["content"] == "["


def test_generate_returns_empty_on_malformed_json():
    bad = MagicMock()
    bad.content = [MagicMock(type="text", text="not-json-at-all")]
    client = MagicMock()
    client.messages.create.return_value = bad

    out = generate_proposed_tests(_profile(), client=client)

    assert out == []
