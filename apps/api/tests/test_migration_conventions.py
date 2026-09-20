"""What every migration has to hold to, so upgrading an install that has data and traffic is safe.

The rest of the suite builds its tables with ``create_all`` and never runs a
migration, and the container applies them to whatever database it finds on
start. So the rules live here, read from the files themselves:

* one file per revision, named after it, and a single head, so ``upgrade head``
  always has one answer (a stray copy of a file breaks both);
* a revision id alembic's version table can store;
* nothing that names a schema: migrations run under whatever ``search_path`` the
  deployment gives them;
* a ``downgrade()`` that does something, which is the way back;
* ``conversations`` before the channel tables, because that is the order a reply
  locks them in, and the opposite order deadlocks against live traffic;
* removing data is a decision, written down with a ``# contract: reviewed`` line
  that says why the previous release still works or what the operator must do.

The last two apply to migrations newer than ``LAST_BEFORE_THESE_RULES``; merged
migrations are never edited.
"""

import ast
import pathlib
import re

VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions"
MAX_REVISION_LENGTH = 32  # alembic_version.version_num is VARCHAR(32)
LAST_BEFORE_THESE_RULES = 48
MARKER = "contract: reviewed"

_NAMES_A_SCHEMA = re.compile(r"\bpublic\.|search_path|CREATE\s+EXTENSION", re.IGNORECASE)
_REMOVES_DATA = re.compile(
    r"\bdrop_table\(|\bdrop_column\(|\btype_\s*=|\bDELETE\s+FROM\b|\bTRUNCATE\b|\bDROP\s+(TABLE|COLUMN)\b", re.IGNORECASE
)
_CHANNEL_TABLE = re.compile(r"""["'](\w+_channels)["']""")
_CONVERSATIONS = re.compile(r"""["']conversations["']""")


class Migration:
    def __init__(self, path: pathlib.Path):
        self.path = path
        self.source = path.read_text()
        tree = ast.parse(self.source)
        constants = {
            node.targets[0].id: node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
        }
        self.revision = constants.get("revision")
        self.down_revision = constants.get("down_revision")
        self.functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}

    def body(self, name: str) -> str:
        """The function's code without comment lines, so prose about a rule does not trip it."""
        function = self.functions[name]
        lines = self.source.splitlines()[function.lineno - 1 : function.end_lineno]
        return "\n".join(line for line in lines if not line.lstrip().startswith("#"))

    @property
    def number(self) -> int:
        match = re.match(r"(\d+)", self.path.stem)
        return int(match.group(1)) if match else 0


def _migrations() -> list[Migration]:
    found = [Migration(path) for path in sorted(VERSIONS.glob("*.py"))]
    assert found, f"no migrations under {VERSIONS}, so these tests prove nothing"
    return found


def _newer(migrations: list[Migration]) -> list[Migration]:
    return [m for m in migrations if m.number > LAST_BEFORE_THESE_RULES]


def test_each_revision_lives_in_one_file_named_after_it():
    offenders = [f"{m.path.name} declares {m.revision!r}" for m in _migrations() if m.revision != m.path.stem]
    assert not offenders, (
        "A migration file is named after its revision, and nothing else may sit in versions/ "
        "(a copy of a file declares the same revision twice):\n  " + "\n  ".join(offenders)
    )


def test_there_is_one_head_and_no_gap():
    migrations = _migrations()
    revisions = {m.revision for m in migrations}
    parents = {m.down_revision for m in migrations if m.down_revision}
    heads = sorted(revisions - parents)
    assert len(heads) == 1, f"`alembic upgrade head` needs exactly one head, found {heads}. Rebase the newer migration onto the other."
    missing = sorted(parents - revisions)
    assert not missing, f"down_revision points at a revision no file declares: {missing}"


def test_revision_ids_fit_the_version_table():
    too_long = [f"{m.revision} ({len(m.revision)})" for m in _migrations() if len(m.revision or "") > MAX_REVISION_LENGTH]
    assert not too_long, f"alembic stores the revision in VARCHAR({MAX_REVISION_LENGTH}); shorten: {too_long}"


def test_migrations_do_not_name_a_schema():
    offenders = [m.path.name for m in _migrations() if _NAMES_A_SCHEMA.search(m.body("upgrade"))]
    assert not offenders, (
        "Leave table names unqualified and do not set search_path or create extensions: a migration runs "
        f"under the search_path its deployment gives it. Offenders: {offenders}"
    )


def test_every_migration_has_a_way_back():
    offenders = []
    for migration in _migrations():
        function = migration.functions.get("downgrade")
        statements = [
            node for node in (function.body if function else [])
            if not isinstance(node, ast.Pass) and not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
        ]
        if not statements:
            offenders.append(migration.path.name)
    assert not offenders, f"downgrade() is the way back when a release has to be reverted; write one: {offenders}"


def test_conversations_is_locked_before_the_channel_tables():
    offenders = []
    for migration in _newer(_migrations()):
        upgrade = migration.body("upgrade")
        conversations = _CONVERSATIONS.search(upgrade)
        channel = _CHANNEL_TABLE.search(upgrade)
        if conversations and channel and channel.start() < conversations.start():
            offenders.append(f"{migration.path.name}: {channel.group(1)} before conversations")
    assert not offenders, (
        "A reply locks conversations and then the table of the channel it goes out on. A migration that takes "
        "them the other way round deadlocks against that traffic on a busy install, so touch conversations "
        "first:\n  " + "\n  ".join(offenders)
    )


def test_removing_data_is_a_written_decision():
    offenders = [
        m.path.name for m in _newer(_migrations()) if _REMOVES_DATA.search(m.body("upgrade")) and MARKER not in m.source
    ]
    assert not offenders, (
        "These drop a table or column, change a column type, or delete rows. Anyone upgrading applies that to "
        f"their own data, so add a `# {MARKER}` line saying why the previous release keeps working (or what "
        "the operator has to do first), and prefer removing in a later release than the one that stops "
        f"reading it: {offenders}"
    )
