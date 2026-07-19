"""Constrain link templates to a single surface.

Revision ID: 011_link_template_single_surface
Revises: 010_personal_link_templates
Create Date: 2026-06-28
"""
from __future__ import annotations

from typing import Any, Iterable, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "011_link_template_single_surface"
down_revision: Union[str, None] = "010_personal_link_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COPYABLE_COLUMNS = (
    "template_id",
    "name",
    "icon_name",
    "tooltip_template",
    "url_template",
    "field_names",
    "conditions",
    "surface_scopes",
    "entity_types",
    "enabled",
    "display_order",
    "created_at",
    "updated_at",
)
JSONB_COLUMNS = {"field_names", "conditions", "surface_scopes", "entity_types"}


def _has_surface(scopes: Any, surface: str) -> bool:
    return isinstance(scopes, list) and surface in scopes


def _both_surfaces(scopes: Any) -> bool:
    return _has_surface(scopes, "timeline_item") and _has_surface(scopes, "entity")


def _with_copy_suffix(template_id: str, existing_ids: set[str]) -> str:
    candidate = f"{template_id}-entity"
    if candidate not in existing_ids:
        return candidate

    index = 2
    while True:
        candidate = f"{template_id}-entity-{index}"
        if candidate not in existing_ids:
            return candidate
        index += 1


def _copy_name(name: str) -> str:
    return name if name.endswith(" (entity)") else f"{name} (entity)"


def _load_rows(bind: sa.Connection, table_name: str) -> list[dict[str, Any]]:
    result = bind.execute(sa.text(f"SELECT * FROM {table_name} ORDER BY id"))
    return [dict(row) for row in result.mappings()]


def _jsonb_bindparams(column_names: Iterable[str]) -> list[sa.BindParameter[Any]]:
    return [
        sa.bindparam(column_name, type_=postgresql.JSONB(astext_type=sa.Text()))
        for column_name in column_names
        if column_name in JSONB_COLUMNS
    ]


def _update_surface(bind: sa.Connection, table_name: str, row_id: int, surface: str) -> None:
    bind.execute(
        sa.text(f"UPDATE {table_name} SET surface_scopes = :surface_scopes WHERE id = :id").bindparams(
            sa.bindparam("surface_scopes", type_=postgresql.JSONB(astext_type=sa.Text())),
        ),
        {"surface_scopes": [surface], "id": row_id},
    )


def _normalize_table(
    *,
    bind: sa.Connection,
    table_name: str,
    existing_ids: Iterable[str],
    user_scoped: bool,
) -> None:
    all_existing_ids = set(existing_ids)
    per_user_ids: dict[Any, set[str]] = {}

    if user_scoped:
        for row in _load_rows(bind, table_name):
            per_user_ids.setdefault(row["user_id"], set()).add(row["template_id"])

    for row in _load_rows(bind, table_name):
        scopes = row.get("surface_scopes")
        if _both_surfaces(scopes):
            scoped_ids = per_user_ids.setdefault(row["user_id"], set()) if user_scoped else all_existing_ids
            next_template_id = _with_copy_suffix(row["template_id"], scoped_ids)
            scoped_ids.add(next_template_id)
            if not user_scoped:
                all_existing_ids.add(next_template_id)

            insert_columns = list(COPYABLE_COLUMNS)
            insert_values = {column: row[column] for column in insert_columns}
            insert_values["template_id"] = next_template_id
            insert_values["name"] = _copy_name(row["name"])
            insert_values["surface_scopes"] = ["entity"]

            if user_scoped:
                insert_columns.append("user_id")
                insert_values["user_id"] = row["user_id"]

            bind.execute(
                sa.text(
                    f"""
                    INSERT INTO {table_name} ({", ".join(insert_columns)})
                    VALUES ({", ".join(f":{column}" for column in insert_columns)})
                    """
                ).bindparams(*_jsonb_bindparams(insert_columns)),
                insert_values,
            )
            _update_surface(bind, table_name, row["id"], "timeline_item")
        elif _has_surface(scopes, "entity"):
            _update_surface(bind, table_name, row["id"], "entity")
        else:
            _update_surface(bind, table_name, row["id"], "timeline_item")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "link_templates" in table_names:
        columns = {column["name"] for column in inspector.get_columns("link_templates")}
        if "surface_scopes" in columns:
            public_ids = bind.execute(sa.text("SELECT template_id FROM link_templates")).scalars().all()
            _normalize_table(
                bind=bind,
                table_name="link_templates",
                existing_ids=public_ids,
                user_scoped=False,
            )

    if "personal_link_templates" in table_names:
        columns = {column["name"] for column in inspector.get_columns("personal_link_templates")}
        if "surface_scopes" in columns:
            personal_ids = bind.execute(sa.text("SELECT template_id FROM personal_link_templates")).scalars().all()
            _normalize_table(
                bind=bind,
                table_name="personal_link_templates",
                existing_ids=personal_ids,
                user_scoped=True,
            )


def downgrade() -> None:
    # The migration may split one dual-surface template into two separately editable
    # templates. There is no reliable lossless downgrade after users can edit them.
    pass
