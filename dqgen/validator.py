"""Deterministic validation of LLM-proposed tests.

Three checks per proposal:
1. Column exists in the profile.
2. Test name is one we support.
3. Test-specific args are well-formed.

Failed proposals are returned with a human-readable reason so users
can see what Claude tried.
"""
from __future__ import annotations

from dataclasses import dataclass

from dqgen.models import ProposedTest, TableProfile, ValidTest

SUPPORTED_TESTS = {
    "not_null",
    "unique",
    "accepted_values",
    "relationships",
    "dbt_utils.accepted_range",
}


@dataclass
class RejectedTest:
    proposal: ProposedTest
    reason: str


def _check_args(proposal: ProposedTest) -> str | None:
    """Return reason string if args are invalid, else None."""
    args = proposal.args
    if proposal.test == "accepted_values":
        values = args.get("values")
        if not isinstance(values, list) or not values:
            return "accepted_values requires non-empty 'values' list"
    elif proposal.test == "dbt_utils.accepted_range":
        if "min_value" not in args and "max_value" not in args:
            return "accepted_range requires 'min_value' and/or 'max_value'"
    elif proposal.test == "relationships":
        if "to" not in args or "field" not in args:
            return "relationships requires 'to' and 'field'"
    return None


def validate_proposals(
    proposals: list[ProposedTest],
    profile: TableProfile,
) -> tuple[list[ValidTest], list[RejectedTest]]:
    column_names = {c.name for c in profile.columns}
    valid: list[ValidTest] = []
    rejected: list[RejectedTest] = []

    for p in proposals:
        if p.column not in column_names:
            rejected.append(RejectedTest(p, f"column '{p.column}' not in table"))
            continue
        if p.test not in SUPPORTED_TESTS:
            rejected.append(RejectedTest(p, f"unsupported test '{p.test}'"))
            continue
        arg_error = _check_args(p)
        if arg_error:
            rejected.append(RejectedTest(p, arg_error))
            continue
        valid.append(ValidTest(**p.model_dump()))

    return valid, rejected
