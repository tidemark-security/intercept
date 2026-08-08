from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("enabled", "expected"),
    [("false", "False"), ("true", "True")],
)
def test_dummy_data_routes_are_mounted_only_when_explicitly_enabled(
    enabled: str,
    expected: str,
) -> None:
    environment = os.environ.copy()
    environment["DUMMY_DATA_ENABLED"] = enabled
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.main import api_app; "
                "print(any(getattr(route, 'path', '').startswith('/api/v1/dummy-data') "
                "for route in api_app.routes))"
            ),
        ],
        cwd=BACKEND_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip().splitlines()[-1] == expected
