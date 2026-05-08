from dqgen.models import ColumnProfile, ProposedTest, TableProfile
from dqgen.validator import validate_proposals


def _profile() -> TableProfile:
    return TableProfile(
        schema="raw",
        name="orders",
        row_count=100,
        columns=[
            ColumnProfile(name="id", dtype="INTEGER", nullable=False, null_count=0, distinct_count=100),
            ColumnProfile(name="status", dtype="VARCHAR", nullable=False, null_count=0, distinct_count=3),
        ],
    )


def test_validate_passes_well_formed_proposal():
    proposals = [ProposedTest(column="id", test="not_null", args={}, rationale="PK")]
    valid, rejected = validate_proposals(proposals, _profile())
    assert len(valid) == 1 and len(rejected) == 0


def test_validate_rejects_unknown_column():
    proposals = [ProposedTest(column="nope", test="not_null", args={}, rationale="...")]
    valid, rejected = validate_proposals(proposals, _profile())
    assert len(valid) == 0
    assert "column" in rejected[0].reason.lower()


def test_validate_rejects_unknown_test_name():
    proposals = [ProposedTest(column="id", test="frobnicate", args={}, rationale="...")]
    valid, rejected = validate_proposals(proposals, _profile())
    assert len(valid) == 0
    assert "test" in rejected[0].reason.lower()


def test_validate_rejects_accepted_values_without_values():
    proposals = [ProposedTest(column="status", test="accepted_values", args={}, rationale="...")]
    valid, rejected = validate_proposals(proposals, _profile())
    assert len(valid) == 0


def test_validate_accepts_accepted_values_with_values():
    proposals = [ProposedTest(
        column="status", test="accepted_values",
        args={"values": ["placed", "shipped", "completed"]},
        rationale="3 stable values",
    )]
    valid, rejected = validate_proposals(proposals, _profile())
    assert len(valid) == 1


def test_validate_rejects_accepted_range_without_bounds():
    proposals = [ProposedTest(column="id", test="dbt_utils.accepted_range", args={}, rationale="...")]
    valid, rejected = validate_proposals(proposals, _profile())
    assert len(valid) == 0


def test_validate_accepts_accepted_range_with_min_only():
    proposals = [ProposedTest(
        column="id", test="dbt_utils.accepted_range",
        args={"min_value": 0}, rationale="non-negative",
    )]
    valid, rejected = validate_proposals(proposals, _profile())
    assert len(valid) == 1


def test_validate_rejects_relationships_without_to_and_field():
    proposals = [ProposedTest(
        column="id", test="relationships", args={"to": "ref('users')"}, rationale="...",
    )]
    valid, rejected = validate_proposals(proposals, _profile())
    assert len(valid) == 0
