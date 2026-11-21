from collections.abc import Sequence

from sqlalchemy import ColumnElement, SQLColumnExpression, or_


UNASSIGNED_ASSIGNEE = "__unassigned__"


def append_assignee_filter(
    filters: list[ColumnElement[bool]],
    assignee_column: SQLColumnExpression[str | None],
    assignees: Sequence[str] | None,
) -> None:
    """Append one OR condition so assignees combine with other filters via AND."""
    selected = {value for value in assignees or () if value}
    clauses = []
    if UNASSIGNED_ASSIGNEE in selected:
        clauses.append(assignee_column.is_(None))
        selected.remove(UNASSIGNED_ASSIGNEE)
    if selected:
        clauses.append(assignee_column.in_(sorted(selected)))
    if clauses:
        filters.append(or_(*clauses))
