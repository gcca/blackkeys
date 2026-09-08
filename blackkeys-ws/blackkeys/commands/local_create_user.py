from __future__ import annotations

import asyncio

from blackkeys.application import AuthService
from blackkeys.backends.stores.cache import UserAuthKey
from turso.lib_aio import connect as connect_local

INSERT_USER_SQL = (
    'INSERT INTO "user" (username, password, email) VALUES (?, ?, ?)'
)


async def LocalCreateUser(
    username: str,
    password: str,
    email: str,
    db: str = "./blackkeys.db",
) -> None:
    """Insert a user directly into an existing local SQLite database."""
    UserAuthKey(username)
    if not password:
        raise ValueError("password must not be empty")
    if not email:
        raise ValueError("email must not be empty")

    connection = await connect_local(db)
    try:
        password_hash = await asyncio.to_thread(
            AuthService.password_hasher.hash, password
        )
        await connection.execute(
            INSERT_USER_SQL, (username, password_hash, email)
        )
        await connection.commit()
    finally:
        await connection.close()
