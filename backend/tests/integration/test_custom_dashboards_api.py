from datetime import datetime, timedelta, timezone

from app.models.enums import AlertStatus, CaseStatus, Priority, TaskStatus
from app.models.models import Alert, Case, Task
from tests.fixtures.auth import DEFAULT_TEST_PASSWORD

PATH = "/api/v1/custom-dashboards"
TRIAGE = f"{PATH}/triage-queue-health"


async def login(client, session_maker, user):
    async with session_maker() as db:
        db.add(user)
        await db.commit()
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": user.username, "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    token = response.cookies["intercept_session"]
    client.cookies.clear()
    return {"Cookie": f"intercept_session={token}"}


def widget(id, measure, order, *, display="number", group=None, **settings):
    return {
        "id": id, "title": id, "measure": measure, "display": display, "group_by": group,
        "layout": {"order": order}, **settings,
    }


async def evaluate(client, headers, definition, **settings):
    response = await client.post(
        f"{PATH}/evaluate", headers=headers, json={"definition": definition, **settings},
    )
    assert response.status_code == 200, response.text
    results = {item["widget_id"]: item for item in response.json()["results"]}
    assert all(item["error"] is None for item in results.values()), results
    return results


async def records(client, headers, drill):
    response = await client.post(f"{PATH}/records", headers=headers, json={"reference": drill})
    assert response.status_code == 200, response.text
    return response.json()


async def test_duplicate_customize_and_drill_exact_alerts(client, session_maker, analyst_user_factory):
    user = await login(client, session_maker, analyst_user_factory())
    now = datetime.now(timezone.utc)
    stamp = now - timedelta(days=1)
    async with session_maker() as db:
        db.add_all([
            Alert(title="Rule A", source="sensor", priority=Priority.CRITICAL, created_at=stamp, tags=["identity"]),
            Alert(
                title="Rule A", source="sensor", priority=Priority.CRITICAL, created_at=stamp,
                status=AlertStatus.CLOSED_DUPLICATE, triaged_at=stamp + timedelta(minutes=30),
            ),
            Alert(title="Rule A extended", source="sensor", priority=Priority.CRITICAL, created_at=stamp),
            Alert(title="Wrong source", source="sensor-ext", priority=Priority.CRITICAL, created_at=stamp),
            Alert(title="Wrong priority", source="sensor", priority=Priority.HIGH, created_at=stamp),
            Alert(title="Wrong date", source="sensor", priority=Priority.CRITICAL, created_at=now - timedelta(days=20)),
        ])
        await db.commit()

    starter = (await client.get(TRIAGE, headers=user)).json()
    starter_results = await evaluate(
        client, user, starter["definition"], dashboard_id=starter["id"], revision=starter["revision"],
    )
    assert starter_results["awaiting"]["points"][0]["count"] == 5
    assert starter_results["oldest"]["records"]["items"][0]["title"] == "Wrong date"
    triage_sample = starter_results["triage-time"]["points"][0]
    assert triage_sample["count"] == 1 and triage_sample["value"] == 1800
    copy = await client.post(f"{TRIAGE}/duplicate", headers=user, json={})
    assert copy.status_code == 201
    draft = copy.json()
    config = draft["definition"]
    intake = next(item for item in config["widgets"] if item["id"] == "intake")
    intake.update(
        display="breakdown", group_by="title",
        filters=[
            {"field": "priority", "op": "in", "value": ["CRITICAL"]},
            {"field": "source", "op": "in", "value": ["sensor"]},
        ],
    )
    preview = await evaluate(client, user, config, dashboard_id=draft["id"], revision=draft["revision"])
    group = next(item for item in preview["intake"]["points"] if item["group"] == "Rule A")
    assert group["value"] == 2
    matched = await records(client, user, group["drill"])
    assert matched["total"] == group["count"]
    assert {item["title"] for item in matched["items"]} == {"Rule A"}
    assert {item["status"] for item in matched["items"]} == {"NEW", "CLOSED_DUPLICATE"}

    url = f"{PATH}/{draft['id']}"
    saved = await client.put(url, headers=user, json={
        "title": "Critical intake", "definition": config, "revision": draft["revision"],
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 2
    assert (await client.get(TRIAGE, headers=user)).json() == starter
    listing = (await client.get(PATH, headers=user)).json()
    assert any(item["title"] == "Critical intake" and item["scope"] == "personal" for item in listing)


async def test_case_samples_and_task_drills_preserve_record_grain(client, session_maker, analyst_user_factory):
    user = await login(client, session_maker, analyst_user_factory())
    now = datetime.now(timezone.utc)
    closed = now - timedelta(hours=2)
    opened = closed - timedelta(hours=30)
    async with session_maker() as db:
        late = Case(title="Late", created_by="tester", status=CaseStatus.CLOSED, created_at=opened, closed_at=closed)
        db.add_all([
            late,
            Case(title="On target", created_by="tester", status=CaseStatus.CLOSED,
                 created_at=closed - timedelta(hours=24), closed_at=closed),
            Case(title="Reopened", created_by="tester", status=CaseStatus.IN_PROGRESS, created_at=opened, closed_at=closed),
            Case(title="Invalid timestamp", created_by="tester", status=CaseStatus.CLOSED, created_at=closed, closed_at=opened),
        ])
        await db.flush()
        db.add_all([
            Alert(title="Child alert", case_id=late.id) for _ in range(2)
        ] + [
            Task(title="Child task", created_by="tester", case_id=late.id, status=TaskStatus.DONE, due_date=opened)
            for _ in range(3)
        ] + [
            Task(title="Standalone", created_by="tester", status=TaskStatus.TODO, due_date=opened)
        ])
        await db.commit()
    source = (await client.get(f"{PATH}/case-response-performance", headers=user)).json()
    result = await evaluate(client, user, source["definition"], dashboard_id=source["id"], revision=0, timezone="Australia/Brisbane")
    duration = result["resolution"]["points"][0]
    assert duration["count"] == 2
    assert duration["excluded_count"] == 1
    assert duration["value"] == 27 * 3600
    miss = result["miss-rate"]["points"][0]
    assert (miss["value"], miss["count"], miss["eligible_count"]) == (50, 1, 2)
    assert [item["title"] for item in (await records(client, user, miss["drill"]))["items"]] == ["Late"]
    assert (await records(client, user, miss["eligible_drill"]))["total"] == 2
    assert [item["title"] for item in result["open-past-target"]["records"]["items"]] == ["Reopened"]
    assert [item["title"] for item in result["overdue"]["records"]["items"]] == ["Standalone"]


async def test_ownership_publish_revisions_and_session_bound_drill(
    client, session_maker, analyst_user_factory, admin_user_factory, auditor_user_factory,
):
    analyst = await login(client, session_maker, analyst_user_factory())
    admin = await login(client, session_maker, admin_user_factory())
    auditor = await login(client, session_maker, auditor_user_factory())
    config = {"widgets": [widget("volume", "alerts.received", 0)]}
    payload = {"title": "SOC workload", "definition": config}
    assert (await client.get(PATH)).status_code == 401
    assert (await client.post(PATH, headers=auditor, json=payload)).status_code == 403
    assert (await client.post(PATH, headers=analyst, json={**payload, "scope": "organization"})).status_code == 403
    owner = (await client.post(PATH, headers=admin, json=payload)).json()
    url = f"{PATH}/{owner['id']}"
    assert (await client.get(url, headers=analyst)).status_code == 404
    assert (await client.post(
        f"{PATH}/evaluate", headers=analyst,
        json={"definition": config, "dashboard_id": owner["id"], "revision": 1},
    )).status_code == 404
    update = {**payload, "scope": "organization", "revision": 1}
    published = await client.put(url, headers=admin, json=update)
    assert published.status_code == 200, published.text
    assert (await client.put(url, headers=admin, json=update)).status_code == 409
    assert (await client.get(url, headers=auditor)).json()["can_edit"] is False
    assert (await client.put(url, headers=analyst, json={**update, "scope": "personal"})).status_code == 403
    assert (await client.post(f"{url}/duplicate", headers=auditor, json={})).status_code == 403
    assert (await client.post(f"{url}/duplicate", headers=analyst, json={})).status_code == 201

    result = await evaluate(client, auditor, {}, dashboard_id=owner["id"], revision=2)
    reference = result["volume"]["points"][0]["drill"]
    assert (await records(client, auditor, reference))["total"] == 0
    assert (await client.post(f"{PATH}/records", headers=analyst, json={"reference": reference})).status_code == 422
    assert (await client.delete(url, headers=admin, params={"revision": 2})).status_code == 204
    assert (await client.post(f"{PATH}/records", headers=auditor, json={"reference": reference})).status_code == 404
