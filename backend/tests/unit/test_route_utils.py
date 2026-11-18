from app.api.route_utils import find_attachment_item


def test_find_attachment_item_ignores_malformed_legacy_entries() -> None:
    attachment = {"id": "attachment-1", "type": "attachment"}

    assert find_attachment_item(42, "attachment-1") is None  # type: ignore[arg-type]
    found = find_attachment_item(
        [None, "invalid", attachment],  # type: ignore[list-item]
        "attachment-1",
    )
    assert found is attachment
