import pytest

from tests.conftest import _validate_test_database_url


def _url(database_name: str) -> str:
    return f"postgresql+asyncpg://intercept_user:intercept_password@localhost:5432/{database_name}"


@pytest.mark.parametrize(
    "database_name",
    [
        "intercept_test_db",
        "test_intercept",
        "intercept_test",
        "tenant_test_db",
    ],
)
def test_validate_test_database_url_accepts_test_scoped_names(database_name: str) -> None:
    assert _validate_test_database_url(_url(database_name)) == database_name


@pytest.mark.parametrize(
    "database_name",
    [
        "intercept_case_db",
        "postgres",
        "template0",
        "template1",
        "intercept",
        "case_db",
        "Intercept_Test_DB",
        "intercept-test-db",
    ],
)
def test_validate_test_database_url_rejects_unsafe_database_names(database_name: str) -> None:
    with pytest.raises(RuntimeError, match="unsafe database"):
        _validate_test_database_url(_url(database_name))


def test_validate_test_database_url_rejects_empty_database_name() -> None:
    with pytest.raises(RuntimeError, match="does not include a database name"):
        _validate_test_database_url("postgresql+asyncpg://intercept_user:intercept_password@localhost:5432/")


def test_validate_test_database_url_requires_asyncpg_postgres_url() -> None:
    with pytest.raises(RuntimeError, match="postgresql\\+asyncpg"):
        _validate_test_database_url("sqlite:///intercept_test_db")
