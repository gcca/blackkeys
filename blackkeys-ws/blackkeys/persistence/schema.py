from __future__ import annotations

from turso.lib_aio import Connection

EXPECTED_SCHEMA: dict[str, frozenset[str]] = {
    "user": frozenset({"username", "password", "email", "created_at"}),
}

TABLE_DDL: dict[str, str] = {
    "user": (
        'CREATE TABLE IF NOT EXISTS "user" ('
        "username TEXT PRIMARY KEY NOT NULL, "
        "password TEXT NOT NULL, "
        "email TEXT NOT NULL, "
        "created_at INTEGER NOT NULL DEFAULT (unixepoch())"
        ")"
    ),
}


class SchemaValidationError(Exception):
    pass


async def InitSchema(db: Connection | None) -> None:
    if db is None:
        return
    for ddl in TABLE_DDL.values():
        await db.execute(ddl)


async def ValidateSchema(db: Connection | None) -> None:
    if db is None or not EXPECTED_SCHEMA:
        return

    problems: list[str] = []
    table_names = await _TableNames(db)
    for table, expected_columns in EXPECTED_SCHEMA.items():
        if table not in table_names:
            problems.append(f"missing table '{table}'")
            continue

        identifier = table.replace('"', '""')
        columns = {
            row[1]: row
            for row in await (
                await db.execute(f'PRAGMA table_info("{identifier}")')
            ).fetchall()
        }
        missing = expected_columns - columns.keys()
        if missing:
            problems.append(
                f"table '{table}' missing columns: "
                f"{', '.join(sorted(missing))}"
            )

        if table == "user" and "created_at" in expected_columns:
            created_at = columns.get("created_at")
            if created_at is not None:
                problems.extend(_ValidateCreatedAt(created_at))

    if problems:
        raise SchemaValidationError("; ".join(problems))


async def _TableNames(db: Connection) -> set[str]:
    rows = await (
        await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    ).fetchall()
    return {row[0] for row in rows}


def _ValidateCreatedAt(column: tuple) -> list[str]:
    problems: list[str] = []
    if str(column[2]).upper() != "INTEGER":
        problems.append("table 'user' column 'created_at' must use INTEGER")
    if not column[3]:
        problems.append("table 'user' column 'created_at' must be NOT NULL")
    if _NormalizeDefault(column[4]) != "unixepoch()":
        problems.append(
            "table 'user' column 'created_at' must default to unixepoch()"
        )
    return problems


def _NormalizeDefault(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    expression = "".join(value.lower().split())
    if expression.startswith("(") and expression.endswith(")"):
        return expression[1:-1]
    return expression
