from typing import Any, List, Optional

from sqlalchemy import not_


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
