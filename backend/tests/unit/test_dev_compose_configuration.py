from __future__ import annotations

import re
from pathlib import Path

from app.core.password_policy import validate_password_policy


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_default_initial_admin_password_satisfies_password_policy() -> None:
    compose = (PROJECT_ROOT / "dev" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r"^      INITIAL_ADMIN_PASSWORD: \$\{INITIAL_ADMIN_PASSWORD:-(.+)\}$",
        compose,
        re.MULTILINE,
    )

    assert match is not None, (
        "dev Compose must provide an initial admin password default"
    )
    assert validate_password_policy(match.group(1)) == match.group(1)
