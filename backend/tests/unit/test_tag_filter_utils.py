from app.services.tag_filter_utils import merge_persisted_tags, normalize_persisted_tags


def test_normalize_persisted_tags_drops_invalid_values_and_deduplicates_case_insensitively() -> None:
    assert normalize_persisted_tags(
        [" Review ", "review", "", "  ", "Null", "null", None, 42, "Escalated"]
    ) == ["Review", "Escalated"]


def test_merge_persisted_tags_normalizes_existing_and_incoming_tags() -> None:
    assert merge_persisted_tags([" Existing ", "null"], ["existing", " New "]) == [
        "Existing",
        "New",
    ]
