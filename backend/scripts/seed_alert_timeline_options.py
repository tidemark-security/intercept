#!/usr/bin/env python3
"""Populate an alert with every allowed timeline item variant for UI validation.

This mirrors the coverage from backend/tests/integration/test_alert_timeline_items.py:
- simple item types
- every observable variant
- every system variant
- every actor variant
- every network protocol variant
- every registry operation variant

It intentionally excludes item types that alerts reject in that test suite:
task, alert reference, and forensic artifact.

Usage:
    cd backend
    conda activate intercept
    python scripts/seed_alert_timeline_options.py

Optional:
    python scripts/seed_alert_timeline_options.py --alert-id 123
    python scripts/seed_alert_timeline_options.py --title "Timeline UI validation"
    python scripts/seed_alert_timeline_options.py --created-by analyst
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # type: ignore[attr-defined]

backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.api.route_utils import create_timeline_converter, get_timeline_item_types
from app.core.database import engine
from app.models.models import Alert, AlertCreate, AlertTimelineItem, Case
from app.services.alert_service import alert_service


convert_timeline_item = create_timeline_converter(get_timeline_item_types(AlertTimelineItem))


class _ParamValue:
    def __init__(self, *values: Any):
        self.values = values


def _load_timeline_payloads_module() -> ModuleType:
    fixture_path = backend_path / "tests" / "fixtures" / "timeline_payloads.py"
    if not fixture_path.exists():
        raise FileNotFoundError(f"Timeline payload fixture not found: {fixture_path}")

    try:
        import pytest  # type: ignore
    except ImportError:
        pytest = ModuleType("pytest")
        pytest.param = lambda *values, **_: _ParamValue(*values)  # type: ignore[attr-defined]
        sys.modules["pytest"] = pytest

    spec = importlib.util.spec_from_file_location("seed_timeline_payloads", fixture_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module spec from {fixture_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


timeline_payloads = _load_timeline_payloads_module()

EXTERNAL_ACTOR_VARIANTS = timeline_payloads.EXTERNAL_ACTOR_VARIANTS
INTERNAL_ACTOR_VARIANTS = timeline_payloads.INTERNAL_ACTOR_VARIANTS
OBSERVABLE_VARIANTS = timeline_payloads.OBSERVABLE_VARIANTS
PROTOCOL_VARIANTS = timeline_payloads.PROTOCOL_VARIANTS
REGISTRY_OP_VARIANTS = timeline_payloads.REGISTRY_OP_VARIANTS
SYSTEM_TYPE_VARIANTS = timeline_payloads.SYSTEM_TYPE_VARIANTS
THREAT_ACTOR_VARIANTS = timeline_payloads.THREAT_ACTOR_VARIANTS
make_attachment = timeline_payloads.make_attachment
make_case_ref = timeline_payloads.make_case_ref
make_email_item = timeline_payloads.make_email_item
make_external_actor = timeline_payloads.make_external_actor
make_internal_actor = timeline_payloads.make_internal_actor
make_link = timeline_payloads.make_link
make_network_traffic = timeline_payloads.make_network_traffic
make_note = timeline_payloads.make_note
make_observable = timeline_payloads.make_observable
make_process = timeline_payloads.make_process
make_registry_change = timeline_payloads.make_registry_change
make_system = timeline_payloads.make_system
make_threat_actor = timeline_payloads.make_threat_actor
make_ttp = timeline_payloads.make_ttp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Populate an alert with every allowed timeline item variant.",
    )
    parser.add_argument(
        "--alert-id",
        type=int,
        help="Existing alert ID to populate. If omitted, a new alert is created.",
    )
    parser.add_argument(
        "--title",
        default="Alert timeline option validation",
        help="Title for a newly created alert.",
    )
    parser.add_argument(
        "--description",
        default="Seeded alert containing every allowed timeline item option for UI validation.",
        help="Description for a newly created alert.",
    )
    parser.add_argument(
        "--source",
        default="TimelineOptionSeeder",
        help="Source for a newly created alert.",
    )
    parser.add_argument(
        "--created-by",
        default="seed-script",
        help="Username recorded in audit/timeline metadata.",
    )
    return parser.parse_args()


def _parameter_values(parameter: Any) -> tuple[Any, ...]:
    values = getattr(parameter, "values", None)
    if values is None:
        if isinstance(parameter, tuple):
            return parameter
        return (parameter,)
    return tuple(values)


def build_timeline_payloads(case_id: int) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = [
        make_note("seed-note"),
        make_attachment("seed-attachment"),
        make_ttp("seed-ttp"),
        make_link("seed-link"),
        make_email_item("seed-email"),
        make_process("seed-process"),
        make_case_ref(case_id, item_id="seed-case-ref"),
    ]

    for observable_variant in OBSERVABLE_VARIANTS:
        observable_type, observable_value = _parameter_values(observable_variant)
        payloads.append(
            make_observable(
                observable_type,
                observable_value,
                item_id=f"seed-obs-{str(observable_type).lower()}",
            )
        )

    for system_variant in SYSTEM_TYPE_VARIANTS:
        (system_type,) = _parameter_values(system_variant)
        payloads.append(make_system(system_type, item_id=f"seed-system-{str(system_type).lower()}"))

    for index, internal_actor_variant in enumerate(INTERNAL_ACTOR_VARIANTS, start=1):
        (kwargs,) = _parameter_values(internal_actor_variant)
        payloads.append(make_internal_actor(item_id=f"seed-internal-actor-{index}", **kwargs))

    for index, external_actor_variant in enumerate(EXTERNAL_ACTOR_VARIANTS, start=1):
        (kwargs,) = _parameter_values(external_actor_variant)
        payloads.append(make_external_actor(item_id=f"seed-external-actor-{index}", **kwargs))

    for index, threat_actor_variant in enumerate(THREAT_ACTOR_VARIANTS, start=1):
        (kwargs,) = _parameter_values(threat_actor_variant)
        payloads.append(make_threat_actor(item_id=f"seed-threat-actor-{index}", **kwargs))

    for protocol_variant in PROTOCOL_VARIANTS:
        (protocol,) = _parameter_values(protocol_variant)
        payloads.append(make_network_traffic(protocol, item_id=f"seed-network-{str(protocol).lower()}"))

    for registry_variant in REGISTRY_OP_VARIANTS:
        (operation,) = _parameter_values(registry_variant)
        payloads.append(make_registry_change(operation, item_id=f"seed-registry-{str(operation).lower()}"))

    return payloads


async def get_or_create_alert(
    session: AsyncSession,
    *,
    alert_id: int | None,
    title: str,
    description: str,
    source: str,
) -> Alert:
    if alert_id is not None:
        alert = await alert_service.get_alert(session, alert_id)
        if alert is None:
            raise ValueError(f"Alert {alert_id} not found")
        return alert

    return await alert_service.create_alert(
        session,
        AlertCreate(
            title=title,
            description=description,
            source=source,
        ),
    )


async def create_reference_case(session: AsyncSession, created_by: str, alert_id: int) -> Case:
    case = Case(
        title=f"Timeline validation case for alert {alert_id}",
        description="Reference case created by the alert timeline option seed script.",
        created_by=created_by,
    )
    session.add(case)
    await session.commit()
    await session.refresh(case)
    return case


async def seed_alert_timeline_options(args: argparse.Namespace) -> int:
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as session:
        alert = await get_or_create_alert(
            session,
            alert_id=args.alert_id,
            title=args.title,
            description=args.description,
            source=args.source,
        )
        if alert.id is None:
            raise RuntimeError("Alert ID was not assigned")

        reference_case = await create_reference_case(session, args.created_by, alert.id)
        if reference_case.id is None:
            raise RuntimeError("Reference case ID was not assigned")

        payloads = build_timeline_payloads(reference_case.id)
        seeded_types: list[str] = []

        for payload in payloads:
            typed_item = convert_timeline_item(payload)
            updated_alert = await alert_service.add_timeline_item(
                session,
                alert.id,
                typed_item,
                args.created_by,
            )
            if updated_alert is None:
                raise RuntimeError(f"Alert {alert.id} disappeared while seeding timeline items")
            seeded_types.append(payload["type"])

        final_alert = await alert_service.get_alert(session, alert.id)
        if final_alert is None:
            raise RuntimeError(f"Seeded alert {alert.id} could not be reloaded")

        print("=" * 72)
        print("Alert Timeline Option Seed Complete")
        print("=" * 72)
        print(f"Alert ID: ALT-{alert.id:07d}")
        print(f"Reference case: CAS-{reference_case.id:07d}")
        print(f"Items added in this run: {len(seeded_types)}")
        print(f"Total timeline items now on alert: {len(final_alert.timeline_items or [])}")
        print()
        print("Seeded item counts:")

        counts = Counter(seeded_types)
        for item_type in sorted(counts):
            print(f"- {item_type}: {counts[item_type]}")

        print()
        print("Open the alert in the UI and inspect the timeline for rendering coverage.")

    await engine.dispose()
    return 0


async def main() -> int:
    args = parse_args()

    try:
        return await seed_alert_timeline_options(args)
    except Exception as exc:
        print(f"Failed to seed alert timeline options: {exc}")
        await engine.dispose()
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))