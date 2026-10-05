"""The double-booking constraint (plan §5 layer 3, S §A8).

Application code can be wrong, can race, and can be bypassed by anything else
holding a connection - so a provider's calendar is defended by the database
itself:

    no two ACTIVE appointments (hold or confirmed) may overlap in time

Only `PENDING_PAYMENT` and `CONFIRMED` rows are covered. Terminal rows
(`CANCELLED`, `RESCHEDULED`, `EXPIRED`, ...) keep their original timestamps as
history, so including them would make a re-booked slot permanently unbookable.

`btree_gist` provides the `=` operator class for `uuid`; it is created here
`IF NOT EXISTS` because it is a required prerequisite on a fresh database
(`scripts/postgres/init/01-extensions.sql` pre-creates it for docker, and a
managed instance needs it enabled once by an administrator).

The constraint is deliberately immediate, not deferrable: a reschedule retires
the original and inserts the replacement inside one transaction, and an
immediate constraint is what makes the *second* statement fail loudly rather
than queueing both to commit time.

The status literals are frozen here on purpose - a migration must not change
meaning because a choices list was edited later.
"""

from __future__ import annotations

from django.db import migrations

FORWARD_SQL = """
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE appointments ADD CONSTRAINT no_provider_overlap
    EXCLUDE USING gist (
        provider_id WITH =,
        tstzrange(start_at, end_at, '[)') WITH &&
    )
    WHERE (status IN ('PENDING_PAYMENT', 'CONFIRMED'));
"""

REVERSE_SQL = "ALTER TABLE appointments DROP CONSTRAINT IF EXISTS no_provider_overlap;"


class Migration(migrations.Migration):
    dependencies = [("appointments", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
