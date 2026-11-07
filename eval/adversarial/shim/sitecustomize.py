"""adv-injection-v1 shim: point a server subprocess at the fixture backend.

Put on PYTHONPATH (with the repo's src/ and eval/adversarial/) only for this
suite. Python imports sitecustomize at interpreter start, before main.py runs.
If NITRD_ADV_FIXTURE is set, this installs FixtureBackend via the servers'
existing shared.sql.set_backend() hook and logs a "backend" self-check event.
If the variable is set but the install fails, the process exits non-zero, so
a server can never fall through to the warehouse backend (fail closed).
Without the variable it does nothing.
"""

import os
import sys

if os.getenv("NITRD_ADV_FIXTURE"):
    try:
        from fixture_backend import FixtureBackend

        from shared import sql

        _backend = FixtureBackend(
            os.environ["NITRD_ADV_FIXTURE"], os.environ["NITRD_ADV_LOG"]
        )
        sql.set_backend(_backend)
        _backend.log(
            "backend",
            backend=type(sql.get_backend()).__name__,
            arm=_backend.arm,
            argv=sys.argv[1:],
        )
    except Exception as exc:  # noqa: BLE001 - fail closed, never fall through
        sys.stderr.write(f"adv shim: fixture backend not installed: {exc}\n")
        sys.exit(97)
