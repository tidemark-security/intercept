#!/usr/bin/env python3
"""
Seed closure-prone alerts for triage recommendation testing.

Creates alerts with patterns likely to result in BENIGN, FALSE_POSITIVE,
or DUPLICATE recommendations when triaged.

Usage:
    cd backend
    conda activate intercept
    python scripts/seed_closure_triage_alerts.py

Optional:
    python scripts/seed_closure_triage_alerts.py --count 5
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # type: ignore[attr-defined]

backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.core.database import engine
from app.services.dummy_data_service import dummy_data_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed closure-prone alerts for AI triage recommendation testing."
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of alerts to create (default: 5)",
    )
    return parser.parse_args()


async def seed_closure_prone_alerts(count: int) -> int:
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        alerts = await dummy_data_service.generate_closure_prone_alerts(session, count=count)

        print("=" * 70)
        print("Closure-Prone Alert Seed Complete")
        print("=" * 70)
        print(f"Created alerts: {len(alerts)}")
        print()

        for alert in alerts:
            if alert.id is None:
                continue
            print(f"- ALT-{alert.id:07d}: {alert.title} ({alert.source})")

    await engine.dispose()
    return 0


async def main() -> int:
    args = parse_args()

    if args.count <= 0:
        print("Count must be greater than 0")
        return 1

    try:
        return await seed_closure_prone_alerts(args.count)
    except Exception as exc:
        print(f"Failed to seed closure-prone alerts: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
