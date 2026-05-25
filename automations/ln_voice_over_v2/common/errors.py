"""Validation errors for LNVO v2 contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ValidationProblem(BaseModel):
    """One contract validation problem."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    path: str


class ContractValidationError(ValueError):
    """Raised when cross-contract validation finds one or more problems."""

    def __init__(self, problems: list[ValidationProblem]) -> None:
        self.problems = tuple(problems)
        summary = "; ".join(f"{problem.path}: {problem.message}" for problem in problems)
        super().__init__(summary or "contract validation failed")
