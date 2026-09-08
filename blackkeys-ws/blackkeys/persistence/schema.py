from __future__ import annotations

from turso.lib_aio import Connection

EXPECTED_SCHEMA: dict[str, frozenset[str]] = {
    "users": frozenset({"username", "password", "email", "created_at"}),
}

TABLE_DDL: dict[str, str] = {
    "users": (
        "CREATE TABLE IF NOT EXISTS users ("
        "username TEXT PRIMARY KEY NOT NULL, "
        "password TEXT NOT NULL, "
        "email TEXT NOT NULL, "
        "created_at TEXT NOT NULL DEFAULT (datetime('now'))"
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
    for table, expected_columns in EXPECTED_SCHEMA.items():
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        if await cursor.fetchone() is None:
            problems.append(f"missing table '{table}'")
            continue

        columns = {
            row[1]
            for row in await (
                await db.execute(f"PRAGMA table_info({table})")
            ).fetchall()
        }
        missing = expected_columns - columns
        if missing:
            problems.append(
                f"table '{table}' missing columns: "
                f"{', '.join(sorted(missing))}"
            )

    if problems:
        raise SchemaValidationError("; ".join(problems))
