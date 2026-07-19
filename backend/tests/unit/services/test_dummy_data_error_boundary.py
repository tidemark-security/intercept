from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.dummy_data_service import DummyDataService


@pytest.mark.asyncio
async def test_populate_failure_rolls_back_and_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = RuntimeError("database driver secret")
    monkeypatch.setattr(
        DummyDataService,
        "generate_cases",
        AsyncMock(side_effect=failure),
    )
    db = SimpleNamespace(rollback=AsyncMock())

    with pytest.raises(RuntimeError) as exc_info:
        await DummyDataService.populate_dummy_data(db)  # type: ignore[arg-type]

    assert exc_info.value is failure
    db.rollback.assert_awaited_once_with()
