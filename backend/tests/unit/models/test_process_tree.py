import pytest
from pydantic import ValidationError

from app.models.models import ProcessTreeItem


def node(id: str, parent_id: str | None = None) -> dict:
    return {
        "id": id,
        "parent_id": parent_id,
        "process_name": f"{id}.exe",
        "process_id": 0,
    }


def test_accepts_child_before_parent_and_repeated_pids_across_roots():
    snapshot = ProcessTreeItem.model_validate({
        "processes": [node("child", "root"), node("root"), node("other")],
    })
    assert [process.id for process in snapshot.processes if process.parent_id is None] == ["root", "other"]
    assert snapshot.model_dump(mode="json")["processes"][0]["parent_id"] == "root"


@pytest.mark.parametrize(
    ("processes", "error"),
    [
        ([], "at least 1"),
        ([node("root"), node("root")], "must be unique"),
        ([node("child", "missing")], "missing from the snapshot"),
        ([node("root", "root")], "contains a cycle"),
        ([node("first", "second"), node("second", "first")], "contains a cycle"),
        ([{**node("root"), "process_id": "1"}], "valid integer"),
        ([{**node("root"), "started_at": "2026-11-26T09:42:13"}], "timezone"),
    ],
)
def test_rejects_invalid_process_snapshots(processes, error):
    with pytest.raises(ValidationError, match=error):
        ProcessTreeItem.model_validate({"processes": processes})
