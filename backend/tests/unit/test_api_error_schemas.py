from app.api.error_schemas import ValidationErrorResponse, ValidationField


def test_validation_error_fields_have_an_independent_default_list() -> None:
    first = ValidationErrorResponse(message="first")
    first.fields.append(ValidationField(field="username", error="required"))

    second = ValidationErrorResponse(message="second")

    assert first.model_dump() == {
        "message": "first",
        "fields": [{"field": "username", "error": "required"}],
    }
    assert second.model_dump() == {"message": "second", "fields": []}
