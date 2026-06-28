from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


def _load_migration_module():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "db_migrations"
        / "versions"
        / "011_link_template_single_surface.py"
    )
    spec = importlib.util.spec_from_file_location(
        "link_template_single_surface_migration",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _migration_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": 1,
        "template_id": "case-console",
        "name": "Case Console",
        "icon_name": "Link2",
        "tooltip_template": "Open {{human_id}}",
        "url_template": "https://example/{{human_id}}",
        "field_names": ["human_id"],
        "conditions": None,
        "surface_scopes": ["timeline_item"],
        "entity_types": ["case"],
        "enabled": True,
        "display_order": 10,
        "created_at": None,
        "updated_at": None,
    }
    row.update(overrides)
    return row


def test_single_surface_migration_splits_dual_surface_and_defaults_invalid_values(monkeypatch):
    migration = _load_migration_module()
    inserted_rows: list[dict[str, Any]] = []
    updated_rows: list[tuple[int, str]] = []

    rows = [
        _migration_row(
            id=1,
            template_id="case-console",
            surface_scopes=["timeline_item", "entity"],
        ),
        _migration_row(id=2, template_id="missing-surface", surface_scopes=None),
        _migration_row(id=3, template_id="entity-only", surface_scopes=["entity"]),
        _migration_row(id=4, template_id="invalid-only", surface_scopes=["bad"]),
    ]

    class FakeBind:
        def execute(self, statement: Any, params: dict[str, Any] | None = None):
            if "INSERT INTO" in str(statement):
                inserted_rows.append(params or {})

    monkeypatch.setattr(migration, "_load_rows", lambda _bind, _table_name: rows)
    monkeypatch.setattr(
        migration,
        "_update_surface",
        lambda _bind, _table_name, row_id, surface: updated_rows.append((row_id, surface)),
    )

    migration._normalize_table(
        bind=FakeBind(),
        table_name="link_templates",
        existing_ids={"case-console", "case-console-entity"},
        user_scoped=False,
    )

    assert inserted_rows == [
        {
            **{column: rows[0][column] for column in migration.COPYABLE_COLUMNS},
            "template_id": "case-console-entity-2",
            "name": "Case Console (entity)",
            "surface_scopes": ["entity"],
        }
    ]
    assert updated_rows == [
        (1, "timeline_item"),
        (2, "timeline_item"),
        (3, "entity"),
        (4, "timeline_item"),
    ]
