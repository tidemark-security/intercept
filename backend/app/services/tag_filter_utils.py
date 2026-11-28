from typing import Any, List, Optional

from sqlalchemy import not_


DUMMY_DATA_TAG = "tmi_dummy_data"


class ProtectedTagMutationError(ValueError):
    """An ordinary entity mutation attempted to change a protected tag."""


def validate_protected_tag_mutation(
    before: Optional[List[Any]],
    after: Optional[List[Any]],
) -> List[str]:
    """Normalize tags while requiring protected tag values to remain unchanged."""
    normalized_before = normalize_persisted_tags(before)
    normalized_after = normalize_persisted_tags(after)
    protected_key = DUMMY_DATA_TAG.casefold()
    before_protected = {
        tag for tag in normalized_before if tag.casefold() == protected_key
    }
    after_protected = {
        tag for tag in normalized_after if tag.casefold() == protected_key
    }
    if before_protected != after_protected:
        raise ProtectedTagMutationError(
            f"The protected '{DUMMY_DATA_TAG}' tag may only be managed by the dummy-data service"
        )
    return normalized_after


def normalize_tag_filters(tags: Optional[List[str]]) -> List[str]:
    """Trim, deduplicate, and drop blank tag filters while preserving order."""
    normalized: List[str] = []
    seen: set[str] = set()
    for tag in tags or []:
        clean = tag.strip()
        if not clean or clean in seen:
            continue
        normalized.append(clean)
        seen.add(clean)
    return normalized


def normalize_persisted_tags(tags: Optional[List[Any]]) -> List[str]:
    """Trim, deduplicate, and drop invalid tag values before persistence."""
    normalized: List[str] = []
    seen: set[str] = set()
    for tag in tags or []:
        if not isinstance(tag, str):
            continue

        clean = tag.strip()
        key = clean.lower()
        if not clean or key == "null" or key in seen:
            continue

        normalized.append(clean)
        seen.add(key)
    return normalized


def normalize_derived_entity_tags(tags: Optional[List[Any]]) -> List[str]:
    """Normalize inherited tags without copying protected service sentinels."""
    protected_key = DUMMY_DATA_TAG.casefold()
    return [
        tag
        for tag in normalize_persisted_tags(tags)
        if tag.casefold() != protected_key
    ]


def merge_persisted_tags(
    existing_tags: Optional[List[Any]],
    new_tags: Optional[List[Any]],
) -> List[str]:
    """Merge tag collections through the persisted-tag normalizer."""
    return normalize_persisted_tags([*(existing_tags or []), *(new_tags or [])])


def persisted_tag_delta(
    before: Optional[List[Any]],
    after: Optional[List[Any]],
) -> tuple[List[str], List[str]]:
    """Return case-insensitive persisted tag additions and removals."""
    before_by_key = {tag.lower(): tag for tag in normalize_persisted_tags(before)}
    after_by_key = {tag.lower(): tag for tag in normalize_persisted_tags(after)}
    added = [after_by_key[key] for key in sorted(after_by_key.keys() - before_by_key)]
    removed = [
        before_by_key[key] for key in sorted(before_by_key.keys() - after_by_key)
    ]
    return added, removed


def append_tag_filters(
    filters: list[Any],
    tag_column: Any,
    include_tags: Optional[List[str]],
    exclude_tags: Optional[List[str]],
) -> None:
    """Append include/exclude JSON-array tag filters to an existing filter list."""
    for tag in normalize_tag_filters(include_tags):
        filters.append(tag_column.contains([tag]))

    for tag in normalize_tag_filters(exclude_tags):
        filters.append(not_(tag_column.contains([tag])))
