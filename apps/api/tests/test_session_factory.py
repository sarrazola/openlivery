"""Sessions are created in one place, so substituting one reaches every query.

``get_db`` is the seam a deployment overrides to supply its own session: the
suite in conftest does it, and so does anything wanting a read replica, an
instrumented session or a different engine. Code that calls ``SessionLocal()``
directly opts out of that seam, and because such code runs outside a request,
the resulting failure surfaces inside a background task instead of in a
response.
"""

import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[1] / "app"


def test_only_database_module_calls_the_sessionmaker():
    offenders = []
    for path in APP.rglob("*.py"):
        if path.name == "database.py":
            continue  # where the sessionmaker lives and is legitimately called
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if re.search(r"\bSessionLocal\s*\(", line):
                offenders.append(f"{path.relative_to(APP.parent)}:{number}")

    assert not offenders, (
        "These call SessionLocal() directly and so bypass get_db, which means a "
        "substituted session never reaches them. Use new_session() from "
        "app.database instead:\n  " + "\n  ".join(offenders)
    )
