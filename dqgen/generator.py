"""Single-turn structured generation of proposed dbt tests.

We send Claude the table profile and prefill the assistant turn with `[`
to force the response into a JSON array. We parse the array into
`ProposedTest` objects. No tools, no agent loop, no multi-turn — one
profile in, one list of proposals out.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from dqgen.models import ProposedTest, TableProfile

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096

SYSTEM_PROMPT = """You are a senior data engineer specializing in dbt testing.

You receive a JSON profile of one warehouse table. You return a JSON
array of proposed dbt tests for the table.

Allowed test types (use exactly these names):
- "not_null"
- "unique"
- "accepted_values"        (args: {"values": [...]})
- "relationships"          (args: {"to": "ref('other_model')", "field": "id"})
- "dbt_utils.accepted_range" (args: {"min_value": ..., "max_value": ...})

Rules:
- Output ONLY a JSON array. No prose, no markdown, no code fences.
- Every proposal must reference a column that exists in the profile.
- Use rationale to briefly justify each test based on profile evidence
  (e.g. "0% nulls observed, distinct count equals row count → primary key").
- Don't propose redundant tests (e.g. unique + not_null + accepted_values
  on the same column when accepted_values is overkill).
- Don't propose relationships unless the column name strongly suggests
  a foreign key (ends in "_id" and the referenced table is plausible).
- Use ONLY literal scalar values for accepted_range bounds (e.g.
  "min_value": 0 or "max_value": "2030-12-31"). Do NOT use Jinja
  templates like "{{ run_started_at }}" — bounds must be directly
  comparable to the column at SQL evaluation time.

Schema for each element:
{
  "column": "<column name>",
  "test": "<one of the allowed test names>",
  "args": {<test-specific arguments, may be empty>},
  "rationale": "<one sentence>"
}
"""


def _profile_as_user_text(profile: TableProfile) -> str:
    return (
        f"Table: {profile.qualified_name}\n"
        f"Profile JSON:\n```json\n{profile.model_dump_json(indent=2)}\n```\n"
        "Return the JSON array of proposed tests now."
    )


def _parse_json_array(prefill: str, response_text: str) -> list[dict[str, Any]]:
    """Reattach the prefill and parse as JSON, trimming trailing chatter."""
    full = prefill + response_text
    end = full.rfind("]")
    if end == -1:
        return []
    return json.loads(full[: end + 1])


def _extract_text(response: Any) -> str:
    blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
    return "".join(blocks)


def generate_proposed_tests(
    profile: TableProfile,
    *,
    client: Any,
    model: str = MODEL,
) -> list[ProposedTest]:
    prefill = "["
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": _profile_as_user_text(profile)},
            {"role": "assistant", "content": prefill},
        ],
    )

    try:
        parsed = _parse_json_array(prefill, _extract_text(response))
    except json.JSONDecodeError:
        return []

    proposals: list[ProposedTest] = []
    for item in parsed:
        try:
            proposals.append(ProposedTest(**item))
        except (ValidationError, TypeError):
            continue
    return proposals
