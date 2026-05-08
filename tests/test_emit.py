import yaml

from dqgen.emit import emit_rationale, emit_schema_yaml
from dqgen.models import ValidTest


def _tests() -> list[ValidTest]:
    return [
        ValidTest(column="id", test="not_null", args={}, rationale="PK, no nulls"),
        ValidTest(column="id", test="unique", args={}, rationale="distinct == rows"),
        ValidTest(
            column="status",
            test="accepted_values",
            args={"values": ["a", "b"]},
            rationale="2 distinct values",
        ),
    ]


def test_emit_schema_yaml_is_parseable():
    out = emit_schema_yaml(model_name="orders", tests=_tests())
    parsed = yaml.safe_load(out)
    assert parsed["version"] == 2
    assert parsed["models"][0]["name"] == "orders"


def test_emit_schema_yaml_groups_tests_per_column():
    out = emit_schema_yaml(model_name="orders", tests=_tests())
    parsed = yaml.safe_load(out)
    cols = {c["name"]: c for c in parsed["models"][0]["columns"]}
    assert set(cols["id"]["tests"]) == {"not_null", "unique"}


def test_emit_schema_yaml_uses_dict_form_for_parametrized_tests():
    out = emit_schema_yaml(model_name="orders", tests=_tests())
    parsed = yaml.safe_load(out)
    status = next(c for c in parsed["models"][0]["columns"] if c["name"] == "status")
    accepted = status["tests"][0]
    assert "accepted_values" in accepted
    assert accepted["accepted_values"]["values"] == ["a", "b"]


def test_emit_rationale_lists_one_line_per_test():
    out = emit_rationale(_tests())
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) >= 3
    assert any("id.not_null" in line for line in lines)
    assert any("PK, no nulls" in line for line in lines)
