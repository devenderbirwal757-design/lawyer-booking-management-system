"""Reconcile gateway payment state against the local `payments` table.

Runs the same code path as the hourly `payments.reconcile_pending_payments`
beat task (plan §6), so an operator can trigger a sweep by hand after a gateway
outage instead of waiting for the schedule.

Usage:
    python scripts/reconcile_payments.py
    python scripts/reconcile_payments.py --minutes 0 --json

Options:
    `--minutes N`  How far back to look. Defaults to
                    `DJANGO_PAYMENT_RECONCILE_MINUTES`; `0` sweeps every open
                    order regardless of age.
    `--json`       Print the counters as JSON instead of a sentence.

The sweep only ever moves an order *down* (`PENDING` -> `FAILED`) or confirms
one through `mark_captured` when the gateway says paid *and* a captured payment
can be read back. It never invents a success, so it is safe to run repeatedly.

Requires gateway credentials. Outside `DEBUG` a stub gateway refuses to load,
so this exits with the configuration error rather than pretending to reconcile.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _load_django() -> None:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    import django

    django.setup()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--minutes",
        type=int,
        default=None,
        help="only check orders older than this many minutes (default: settings)",
    )
    parser.add_argument("--json", action="store_true", help="print counters as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.minutes is not None and args.minutes < 0:
        print("--minutes cannot be negative", file=sys.stderr)
        return 2
    _load_django()

    from apps.payments import services

    try:
        stats = services.reconcile_pending_payments(older_than_minutes=args.minutes)
    except Exception as exc:
        print(f"reconcile_payments failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(stats, indent=2, sort_keys=True))
    else:
        print(
            f"checked {stats['checked']} open order(s): "
            f"{stats['captured']} captured, {stats['failed']} failed, "
            f"{stats['unavailable']} gateway unavailable, {stats['unmatched']} unmatched."
        )
    # A gateway outage is a real outcome, not a script failure: the sweep ran,
    # it just could not reach the truth. Anything else still returns 0.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
