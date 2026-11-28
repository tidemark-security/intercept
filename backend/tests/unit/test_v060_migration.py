from pathlib import Path

from alembic.script import ScriptDirectory


def test_v060_is_one_revision_from_the_released_v05_schema() -> None:
    scripts = ScriptDirectory(str(Path(__file__).resolve().parents[2] / "db_migrations"))
    revisions = scripts.iterate_revisions("032_timeline_authoring_receipts", "012_nhi_override_timestamps")

    assert [step.revision for step in revisions] == ["032_timeline_authoring_receipts"]
