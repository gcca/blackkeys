from __future__ import annotations

from dataclasses import dataclass

from turso import IntegrityError
from turso.lib_aio import Connection

from blackkeys.persistence.turso import PushDatabase


class UserUnavailable(Exception):
    pass


class UserConflict(Exception):
    pass


@dataclass(frozen=True, slots=True)
class DbUserAuth:
    username: str
    password: str


class DbStore:
    __slots__ = ("_db",)

    def __init__(self, db: Connection | None = None) -> None:
        self._db = db

    @property
    def db(self) -> Connection | None:
        return self._db

    @db.setter
    def db(self, db: Connection | None) -> None:
        self._db = db

    async def ReadUser(self, username: str) -> DbUserAuth | None:
        db = self._db
        if db is None:
            raise UserUnavailable
        try:
            cursor = await db.execute(
                'SELECT username, password FROM "user" WHERE username = ?',
                (username,),
            )
            row = await cursor.fetchone()
        except Exception as error:
            raise UserUnavailable from error
        if row is None:
            return None
        if (
            len(row) != 2
            or not isinstance(row[0], str)
            or not isinstance(row[1], str)
            or not row[0]
            or not row[1]
        ):
            raise UserUnavailable
        return DbUserAuth(row[0], row[1])

    async def CreateUser(
        self, username: str, password: str, email: str
    ) -> None:
        db = self._db
        if db is None:
            raise UserUnavailable
        try:
            await db.execute(
                'INSERT INTO "user" (username, password, email)'
                " VALUES (?, ?, ?)",
                (username, password, email),
            )
            await db.commit()
        except IntegrityError as error:
            raise UserConflict from error
        except Exception as error:
            raise UserUnavailable from error
        await PushDatabase(db)
