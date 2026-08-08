"""Shared validation-error response schemas for HTTP APIs."""

from pydantic import BaseModel, Field


class ValidationField(BaseModel):
    field: str
    error: str


class ValidationErrorResponse(BaseModel):
    message: str
    fields: list[ValidationField] = Field(default_factory=list)
