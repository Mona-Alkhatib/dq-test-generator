"""Pydantic types used throughout the pipeline.

These types form the strict contract between profiler → generator →
validator → emit. Each stage takes one model in and returns another.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    nullable: bool
    null_count: int
    distinct_count: int
    min_value: Any | None = None
    max_value: Any | None = None
    mean_value: float | None = None
    top_values: list[tuple[Any, int]] = Field(default_factory=list)

    def distinct_to_row_ratio(self, row_count: int) -> float:
        if row_count == 0:
            return 0.0
        return self.distinct_count / row_count


class TableProfile(BaseModel):
    schema: str
    name: str
    row_count: int
    columns: list[ColumnProfile]

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}"

    def column(self, name: str) -> ColumnProfile:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(name)


class ProposedTest(BaseModel):
    column: str
    test: str
    args: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class ValidTest(ProposedTest):
    """A ProposedTest that has passed validation. Same fields, distinct type."""
