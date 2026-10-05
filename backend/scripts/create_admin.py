"""Create or promote a Django superuser.

Usage:
    python manage.py createsuperuser --noinput --email admin@example.com
    python scripts/create_admin.py admin@example.com
    ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD='...' python scripts/create_admin.py

With no email argument the script prompts. The password is read from
`ADMIN_PASSWORD` or the terminal - never from `argv`, so it does not end up in
the shell history or `ps` output.

The full demo seed (tenant + admin + provider) is Phase 1/Phase 3's
`seed_demo`; this script only guarantees a usable superuser login.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or promote a Django superuser (email + password login).",
    )
    parser.add_argument(
        "email",
        nargs="?",
        default=None,
        help="Login email. Falls back to $ADMIN_EMAIL, then an interactive prompt.",
    )
    parser.add_argument(
        "--noinput",
        action="store_true",
        help="Never prompt; fail instead if the email or password is missing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

    import django

    django.setup()

    from apps.accounts.models import User

    email = (args.email or os.environ.get("ADMIN_EMAIL", "")).strip()
    if not email:
        if args.noinput:
            print("Email is required: pass it as an argument or set $ADMIN_EMAIL.", file=sys.stderr)
            return 1
        email = input("Email: ").strip()

    password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        if args.noinput:
            print(
                "Password is required: set $ADMIN_PASSWORD (it is never read from argv).",
                file=sys.stderr,
            )
            return 1
        password = getpass.getpass("Password: ")
        if not password:
            print("Password is required.", file=sys.stderr)
            return 1

    user, created = User.objects.get_or_create(
        email=email.lower(),
        defaults={"is_staff": True, "is_superuser": True, "is_active": True},
    )
    if not created:
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
    user.set_password(password)
    user.save()

    action = "Created" if created else "Updated"
    print(f"{action} admin: {user.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
