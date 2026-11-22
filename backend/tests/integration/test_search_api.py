"""Integration tests for search API endpoints.

These tests verify the search API behavior including:
- Authentication requirements
- Query validation
- Response structure

These tests require PostgreSQL due to the use of JSONB columns and full-text
search functionality. The backend test fixture provides PostgreSQL.

To run these tests, configure a PostgreSQL test database:
    export TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:port/testdb
    pytest tests/integration/test_search_api.py -v
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.models.enums import AlertStatus, CaseStatus, TaskStatus
from app.models.models import Alert, Case, Task
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="module", loop_scope="session", autouse=True)
async def search_columns(async_engine: AsyncEngine) -> None:
    """Add migration-managed search objects omitted by SQLModel metadata."""
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        for table_name in ("alerts", "cases", "tasks"):
            await connection.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    "ADD COLUMN IF NOT EXISTS search_vector tsvector"
                )
            )


async def _create_search_alert(
    session_maker: async_sessionmaker[AsyncSession],
    *,
    title: str,
    description: str,
    index_for_fulltext: bool,
) -> None:
    async with session_maker() as session:
        alert = Alert(title=title, description=description, source="search-test")
        session.add(alert)
        await session.flush()
        if index_for_fulltext:
            await session.execute(
                text(
                    "UPDATE alerts "
                    "SET search_vector = to_tsvector('english', title || ' ' || description) "
                    "WHERE id = :alert_id"
                ),
                {"alert_id": alert.id},
            )
        await session.commit()


async def _login_and_get_session(
    client: AsyncClient,
    session_maker: async_sessionmaker[AsyncSession],
    user_factory,
) -> tuple[str, str]:
    """Helper to create user, login, and return (session_cookie, user_id)."""
    user = user_factory()
    
    async with session_maker() as session:
        session.add(user)
        await session.commit()
    
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert login_response.status_code == 200
    session_cookie = login_response.cookies.get("intercept_session")
    assert session_cookie is not None
    
    return session_cookie, str(user.id)


@pytest.mark.parametrize(("entity_type", "model", "prefix", "allowed", "closed"), [
    ("alert", Alert, "ALT", AlertStatus.NEW, AlertStatus.CLOSED_TP),
    ("case", Case, "CAS", CaseStatus.NEW, CaseStatus.CLOSED),
    ("task", Task, "TSK", TaskStatus.TODO, TaskStatus.DONE),
])
async def test_queue_search_filters_before_sorting_counting_and_paging(
    client, session_maker, analyst_user_factory, entity_type, model, prefix, allowed, closed,
):
    session_cookie, _ = await _login_and_get_session(client, session_maker, analyst_user_factory)
    cookies = {"intercept_session": session_cookie}
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    newer = datetime(2022, 1, 1, tzinfo=timezone.utc)
    owner = {"source": "queue test"} if entity_type == "alert" else {"created_by": "test"}

    async with session_maker() as session:
        matched = [
            model(title="QuartzMarker named", assignee="analyst", tags=["keep", "required"], created_at=newer, **owner),
            model(title="QuartzMarker unassigned", tags=["keep", "required"], created_at=old, **owner),
            model(
                title="Timeline-only match", assignee="analyst", tags=["keep", "required"], created_at=old,
                timeline_items={"note-1": {"type": "note", "description": "QuartzMarker"}}, **owner,
            ),
        ]
        session.add_all([
            *matched,
            model(title="QuartzMarker other assignee", assignee="other", tags=["keep", "required"], **owner),
            model(title="QuartzMarker excluded tag", tags=["keep", "required", "noise"], **owner),
            model(title="QuartzMarker missing tag", tags=["keep"], **owner),
            model(title="QuartzMarker wrong status", status=closed, tags=["keep", "required"], **owner),
            # Also presents a content hit but belongs to another entity type.
            (Task(title="QuartzMarker other type", created_by="test") if entity_type != "task"
             else Alert(title="QuartzMarker other type", source="test")),
        ])
        await session.flush()
        named, unassigned, timeline = [row.id for row in matched]
        await session.execute(text("""
            UPDATE alerts SET search_vector = to_tsvector('english', title);
        """))
        await session.execute(text("""
            UPDATE cases SET search_vector = to_tsvector('english', title);
        """))
        await session.execute(text("""
            UPDATE tasks SET search_vector = to_tsvector('english', title);
        """))
        await session.commit()

    params = {
        "q": "QuartzMarker", "entity_type": entity_type,
        "status": [allowed.value, "IN_PROGRESS"], "assignee": ["analyst", "__unassigned__"],
        "include_tags": ["keep", "required"], "exclude_tags": "noise", "sort_order": "asc",
    }

    async def search(**overrides):
        response = await client.get("/api/v1/search/queue", params={**params, **overrides}, cookies=cookies)
        assert response.status_code == 200, response.text
        return response.json()

    for offset, expected in enumerate([timeline, unassigned, named]):
        page = await search(skip=offset, limit=1)
        assert page["total"] == 3
        assert [item["id"] for item in page["results"]] == [expected]
    assert (await search(skip=3, limit=1))["total"] == 3
    assert (await search(skip=3, limit=1))["results"] == []
    assert [item["id"] for item in (await search(start_date="2021-01-01"))["results"]] == [named]
    assert {item["id"] for item in (await search(end_date="2021-01-01"))["results"]} == {unassigned, timeline}
    assert (await search(q=f"{prefix}-{named}"))["total"] == 1
    assert (await search(q=f"{prefix}-{named}", assignee=["__unassigned__"]))["total"] == 0
    assert (await search(q="TSK-1" if entity_type != "task" else "ALT-1"))["total"] == 0

    global_response = await client.get(
        "/api/v1/search", params={"q": "QuartzMarker", "entity_type": entity_type}, cookies=cookies,
    )
    assert global_response.status_code == 200
    assert not {named, unassigned, timeline}.intersection(
        item["entity_id"] for item in global_response.json()["results"]
    )


async def test_queue_search_fuzzy_fallback_respects_queue_filters(client, session_maker, analyst_user_factory):
    session_cookie, _ = await _login_and_get_session(client, session_maker, analyst_user_factory)
    await _create_search_alert(session_maker, title="Phishing", description="", index_for_fulltext=False)
    for assignee, expected in [("__unassigned__", 1), ("other", 0)]:
        response = await client.get(
            "/api/v1/search/queue",
            params={"q": "phising", "entity_type": "alert", "assignee": assignee},
            cookies={"intercept_session": session_cookie},
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == expected


@pytest.mark.parametrize(("entity_type", "model", "prefix", "other_prefix"), [
    ("alert", Alert, "ALT", "CAS"),
    ("case", Case, "CAS", "TSK"),
    ("task", Task, "TSK", "ALT"),
])
async def test_global_and_queue_search_match_parity(
    client, session_maker, analyst_user_factory, entity_type, model, prefix, other_prefix,
):
    session_cookie, _ = await _login_and_get_session(client, session_maker, analyst_user_factory)
    created_at = datetime(2025, 1, 15, tzinfo=timezone.utc)
    owner = {"source": "parity test"} if entity_type == "alert" else {"created_by": "test"}
    numeric_with_content = 613570
    numeric_with_fallback = 734205
    missing_id = f"{prefix}-9999998"

    async with session_maker() as session:
        content = model(
            title=f"{numeric_with_content} observed", created_at=created_at, **owner,
            timeline_items={"note-1": {"type": "note", "description": str(numeric_with_content)}},
        )
        timeline_only = model(
            title="Timeline-only match", created_at=created_at, **owner,
            timeline_items={"note-1": {"type": "note", "description": str(numeric_with_content)}},
        )
        fuzzy_only = model(title="734206", created_at=created_at, **owner)
        indexed = [
            content,
            model(id=numeric_with_content, title=str(numeric_with_content), created_at=created_at, **owner),
            model(id=numeric_with_fallback, title=str(numeric_with_fallback), created_at=created_at, **owner),
            model(title=str(numeric_with_fallback), created_at=datetime(2024, 1, 1, tzinfo=timezone.utc), **owner),
            model(title=missing_id, created_at=created_at, **owner),
            model(title=f"{prefix}-{numeric_with_content:07d}", created_at=created_at, **owner),
        ]
        session.add_all([
            *indexed, timeline_only, fuzzy_only,
            model(title="613571", created_at=created_at, **owner),
        ])
        await session.flush()
        content_id, timeline_id, fuzzy_id = content.id, timeline_only.id, fuzzy_only.id
        await session.execute(
            text(
                f"UPDATE {model.__tablename__} SET search_vector = to_tsvector('english', title) "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": [row.id for row in indexed]},
        )
        await session.commit()

    for query, expected_ids in [
        (f"{prefix.lower()}-{numeric_with_content:07d}", {numeric_with_content}),
        (f"{other_prefix}-{numeric_with_content}", set()),
        (missing_id, set()),
        (str(numeric_with_content), {numeric_with_content, content_id, timeline_id}),
        (str(numeric_with_fallback), {numeric_with_fallback, fuzzy_id}),
    ]:
        # Same entity/date scope; ranking and the returned row shape are intentionally different.
        params = {
            "q": query, "entity_type": entity_type,
            "start_date": "2025-01-01T00:00:00Z", "end_date": "2025-02-01T00:00:00Z",
        }
        for endpoint, id_key in [("/api/v1/search", "entity_id"), ("/api/v1/search/queue", "id")]:
            response = await client.get(
                endpoint, params=params, cookies={"intercept_session": session_cookie},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["total"] == len(body["results"]) == len(expected_ids), (endpoint, query, body)
            assert {row[id_key] for row in body["results"]} == expected_ids, (endpoint, query, body)


@pytest.mark.parametrize(("entity_type", "model"), [
    ("alert", Alert),
    ("case", Case),
    ("task", Task),
])
async def test_global_and_queue_search_substring_parity(
    client, session_maker, analyst_user_factory, entity_type, model,
):
    session_cookie, _ = await _login_and_get_session(client, session_maker, analyst_user_factory)
    owner = {"source": "substring test"} if entity_type == "alert" else {"created_by": "test"}

    async with session_maker() as session:
        full_text = model(
            title="Credential rotation", assignee="analyst",
            created_at=datetime(2025, 1, 10, tzinfo=timezone.utc), **owner,
        )
        title_only = model(
            title="Review of noncredentialed principals", assignee="analyst",
            created_at=datetime(2025, 1, 20, tzinfo=timezone.utc), **owner,
        )
        description_only = model(
            title="Quarterly review", description="The xcredentialy field was present.",
            created_at=datetime(2025, 1, 21, tzinfo=timezone.utc), **owner,
        )
        outside_scope = model(
            title="Legacy noncredentialed principals",
            created_at=datetime(2024, 1, 21, tzinfo=timezone.utc), **owner,
        )
        records = [full_text, title_only, description_only, outside_scope]
        session.add_all(records)
        await session.flush()
        whole_id, title_id, description_id, _ = [row.id for row in records]
        await session.execute(
            text(
                f"UPDATE {model.__tablename__} SET search_vector = "
                "setweight(to_tsvector('english', title), 'A') || "
                "setweight(to_tsvector('english', COALESCE(description, '')), 'B') "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": [row.id for row in records]},
        )
        await session.commit()

    async def search(path, id_key, query, **overrides):
        response = await client.get(
            path,
            params={
                "q": query, "entity_type": entity_type,
                "start_date": "2025-01-01T00:00:00Z", "end_date": "2025-02-01T00:00:00Z", **overrides,
            },
            cookies={"intercept_session": session_cookie},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        return [row[id_key] for row in body["results"]], body["total"]

    global_path, queue_path = "/api/v1/search", "/api/v1/search/queue"
    for path, id_key in [(global_path, "entity_id"), (queue_path, "id")]:
        ids, total = await search(path, id_key, "dEnTi")
        assert set(ids) == {whole_id, title_id, description_id}
        assert total == len(ids) == 3
        assert await search(path, id_key, "cre") == ([description_id, title_id, whole_id], 3)
        assert await search(path, id_key, "de") == ([], 0)
        assert await search(path, id_key, "denti%") == ([], 0)
        assert await search(path, id_key, "denti_") == ([], 0)

    # A full-text hit outranks newer substring hits globally, but the queue
    # still orders by its selected sort and both endpoints count each row once.
    assert await search(global_path, "entity_id", "credential", limit=1) == ([whole_id], 3)
    assert await search(queue_path, "id", "credential", limit=1) == ([description_id], 3)
    assert await search(queue_path, "id", "denti", assignee="__unassigned__") == ([description_id], 1)


async def test_global_search_all_time_includes_older_records_without_changing_default(
    client, session_maker, analyst_user_factory,
):
    session_cookie, _ = await _login_and_get_session(client, session_maker, analyst_user_factory)
    now = datetime.now(timezone.utc)
    async with session_maker() as session:
        recent = Alert(title="Quartzmarker recent", source="test", created_at=now - timedelta(days=2))
        historical = Alert(
            title="Quartzmarker historical", source="test", created_at=now - timedelta(days=400),
        )
        fuzzy = Alert(title="Phishing", source="test", created_at=now - timedelta(days=400))
        session.add_all([recent, historical, fuzzy])
        await session.flush()
        recent_id, historical_id, fuzzy_id = recent.id, historical.id, fuzzy.id
        await session.execute(
            text("UPDATE alerts SET search_vector = to_tsvector('english', title) WHERE id = ANY(:ids)"),
            {"ids": [recent_id, historical_id, fuzzy_id]},
        )
        await session.commit()

    async def search(query, **filters):
        response = await client.get(
            "/api/v1/search",
            params={"entity_type": "alert", "q": query, **filters},
            cookies={"intercept_session": session_cookie},
        )
        assert response.status_code == 200, response.text
        return response.json()

    default = await search("Quartzmarker")
    assert [item["entity_id"] for item in default["results"]] == [recent_id]
    applied = default["date_range"]
    assert datetime.fromisoformat(applied["end"]) - datetime.fromisoformat(applied["start"]) == timedelta(days=30)

    unbounded = await search("Quartzmarker", all_time="true")
    assert unbounded["total"] == 2
    assert {item["entity_id"] for item in unbounded["results"]} == {recent_id, historical_id}
    assert unbounded["date_range"] == {"start": None, "end": None}

    for query, expected in [
        ("*", {recent_id, historical_id, fuzzy_id}),
        (f"ALT-{historical_id:07d}", {historical_id}),
        ("phising", {fuzzy_id}),
    ]:
        assert {item["entity_id"] for item in (await search(query, all_time="true"))["results"]} == expected

    conflict = await client.get(
        "/api/v1/search",
        params={"q": "Quartzmarker", "all_time": "true", "start_date": "2025-01-01"},
        cookies={"intercept_session": session_cookie},
    )
    assert conflict.status_code == 400
    assert conflict.json()["detail"]["code"] == "INVALID_DATE_RANGE"


class TestSearchAuthentication:
    """Tests for search endpoint authentication requirements."""
    
    async def test_search_unauthenticated_returns_401(
        self,
        client: AsyncClient,
    ) -> None:
        """Search endpoint returns 401 for unauthenticated requests."""
        response = await client.get(
            "/api/v1/search",
            params={"q": "test query"},
        )
        
        assert response.status_code == 401
        data = response.json()
        assert "error" in data or "detail" in data or "message" in data
    
    async def test_search_with_invalid_session_returns_401(
        self,
        client: AsyncClient,
    ) -> None:
        """Search endpoint returns 401 for invalid session cookie."""
        response = await client.get(
            "/api/v1/search",
            params={"q": "test query"},
            cookies={"intercept_session": "invalid-session-token"},
        )
        
        assert response.status_code == 401


class TestSearchQueryValidation:
    """Tests for search query parameter validation."""
    
    async def test_search_missing_query_returns_422(
        self,
        client: AsyncClient,
        session_maker: async_sessionmaker[AsyncSession],
        analyst_user_factory,
    ) -> None:
        """Search endpoint returns 422 when q parameter is missing."""
        session_cookie, _ = await _login_and_get_session(
            client, session_maker, analyst_user_factory
        )
        
        response = await client.get(
            "/api/v1/search",
            cookies={"intercept_session": session_cookie},
        )
        
        # FastAPI returns 422 for missing required query params
        assert response.status_code == 422
    
    async def test_search_query_too_short_returns_400(
        self,
        client: AsyncClient,
        session_maker: async_sessionmaker[AsyncSession],
        analyst_user_factory,
    ) -> None:
        """Search endpoint returns 400 when query is less than 2 characters."""
        session_cookie, _ = await _login_and_get_session(
            client, session_maker, analyst_user_factory
        )
        
        response = await client.get(
            "/api/v1/search",
            params={"q": "a"},  # Single character - too short
            cookies={"intercept_session": session_cookie},
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data.get("detail", {}).get("code") == "INVALID_QUERY" or "error" in data
    
    async def test_search_query_too_long_returns_400(
        self,
        client: AsyncClient,
        session_maker: async_sessionmaker[AsyncSession],
        analyst_user_factory,
    ) -> None:
        """Search endpoint returns 400 when query exceeds 200 characters."""
        session_cookie, _ = await _login_and_get_session(
            client, session_maker, analyst_user_factory
        )
        
        # Create query longer than 200 characters
        long_query = "x" * 201
        
        response = await client.get(
            "/api/v1/search",
            params={"q": long_query},
            cookies={"intercept_session": session_cookie},
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data.get("detail", {}).get("code") == "INVALID_QUERY" or "error" in data


class TestSearchInvalidDateRange:
    """Tests for search date range validation."""
    
    async def test_search_invalid_start_date_format_returns_400(
        self,
        client: AsyncClient,
        session_maker: async_sessionmaker[AsyncSession],
        analyst_user_factory,
    ) -> None:
        """Search endpoint returns 400 for invalid start_date format."""
        session_cookie, _ = await _login_and_get_session(
            client, session_maker, analyst_user_factory
        )
        
        response = await client.get(
            "/api/v1/search",
            params={
                "q": "test query",
                "start_date": "not-a-date",
            },
            cookies={"intercept_session": session_cookie},
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "INVALID_DATE" in str(data) or "date" in str(data).lower()
    
    async def test_search_end_before_start_returns_400(
        self,
        client: AsyncClient,
        session_maker: async_sessionmaker[AsyncSession],
        analyst_user_factory,
    ) -> None:
        """Search endpoint returns 400 when end_date is before start_date."""
        session_cookie, _ = await _login_and_get_session(
            client, session_maker, analyst_user_factory
        )
        
        response = await client.get(
            "/api/v1/search",
            params={
                "q": "test query",
                "start_date": "2024-12-31T00:00:00Z",
                "end_date": "2024-01-01T00:00:00Z",  # Before start
            },
            cookies={"intercept_session": session_cookie},
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "INVALID_DATE_RANGE" in str(data) or "date" in str(data).lower()


class TestSearchInvalidEntityTypes:
    """Tests for search entity type parameter validation."""
    
    async def test_search_invalid_entity_type_returns_400(
        self,
        client: AsyncClient,
        session_maker: async_sessionmaker[AsyncSession],
        analyst_user_factory,
    ) -> None:
        """Search endpoint returns 400 for invalid entity_types value."""
        session_cookie, _ = await _login_and_get_session(
            client, session_maker, analyst_user_factory
        )
        
        response = await client.get(
            "/api/v1/search",
            params={
                "q": "test query",
                "entity_type": "invalid_type",
            },
            cookies={"intercept_session": session_cookie},
        )
        
        # Should return 400 for invalid entity type
        # Note: FastAPI might return 422 if enum validation happens at the param level
        assert response.status_code in [400, 422]


class TestSearchResults:
    """Tests for search result functionality (requires PostgreSQL)."""
    
    async def test_search_returns_paginated_search_response_structure(
        self,
        client: AsyncClient,
        session_maker: async_sessionmaker[AsyncSession],
        analyst_user_factory,
    ) -> None:
        """Search endpoint returns proper PaginatedSearchResponse structure."""
        session_cookie, _ = await _login_and_get_session(
            client, session_maker, analyst_user_factory
        )
        await _create_search_alert(
            session_maker,
            title="Test Query Alert",
            description="A searchable integration-test record",
            index_for_fulltext=True,
        )
        
        response = await client.get(
            "/api/v1/search",
            params={"q": "test query"},
            cookies={"intercept_session": session_cookie},
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify PaginatedSearchResponse structure
        assert "results" in data
        assert "total" in data
        assert "skip" in data
        assert "limit" in data
        assert "query" in data
        assert "entity_types" in data
        assert "date_range" in data
        
        # Verify date_range structure
        assert "start" in data["date_range"]
        assert "end" in data["date_range"]
        
        # Verify results is a list
        assert isinstance(data["results"], list)
        assert [result["title"] for result in data["results"]] == ["Test Query Alert"]
    
    async def test_search_no_results_returns_empty_array(
        self,
        client: AsyncClient,
        session_maker: async_sessionmaker[AsyncSession],
        analyst_user_factory,
    ) -> None:
        """Search with no matching results returns empty results array."""
        session_cookie, _ = await _login_and_get_session(
            client, session_maker, analyst_user_factory
        )
        
        # Query for something that won't exist
        response = await client.get(
            "/api/v1/search",
            params={"q": "xyznonexistentquery12345"},
            cookies={"intercept_session": session_cookie},
        )
        
        assert response.status_code == 200
        data = response.json()

        assert data["results"] == []
        assert data["total"] == 0

class TestFuzzySearch:
    """Tests for fuzzy/typo-tolerant search functionality (requires PostgreSQL)."""
    
    async def test_search_typo_phising_finds_phishing(
        self,
        client: AsyncClient,
        session_maker: async_sessionmaker[AsyncSession],
        analyst_user_factory,
    ) -> None:
        """Search with typo 'phising' should find 'Phishing' results via fuzzy fallback."""
        session_cookie, _ = await _login_and_get_session(
            client, session_maker, analyst_user_factory
        )
        await _create_search_alert(
            session_maker,
            title="Phishing Alert",
            description="A suspicious credential-harvesting message",
            index_for_fulltext=False,
        )
        
        response = await client.get(
            "/api/v1/search",
            params={"q": "phising"},  # Common typo of "phishing"
            cookies={"intercept_session": session_cookie},
        )
        
        # Should not error - fuzzy fallback should handle gracefully
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure is valid
        assert "results" in data
        assert "total" in data
        assert "query" in data
        assert data["query"] == "phising"
        assert [result["title"] for result in data["results"]] == ["Phishing Alert"]
    
    async def test_search_fuzzy_similarity_threshold(
        self,
        client: AsyncClient,
        session_maker: async_sessionmaker[AsyncSession],
        analyst_user_factory,
    ) -> None:
        """Fuzzy search should use similarity threshold of 0.3."""
        session_cookie, _ = await _login_and_get_session(
            client, session_maker, analyst_user_factory
        )
        await _create_search_alert(
            session_maker,
            title="Malware Detection",
            description="Endpoint malware was detected",
            index_for_fulltext=False,
        )
        
        # Query with slight variation
        response = await client.get(
            "/api/v1/search",
            params={"q": "malware"},
            cookies={"intercept_session": session_cookie},
        )
        
        assert response.status_code == 200
        data = response.json()

        assert [result["title"] for result in data["results"]] == ["Malware Detection"]
        for result in data["results"]:
            assert "score" in result
            assert 0 <= result["score"] <= 1
