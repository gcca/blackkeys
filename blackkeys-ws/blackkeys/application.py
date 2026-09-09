from __future__ import annotations

import asyncio

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

from blackkeys.repositories import AuthRepository


class AuthService:
    __slots__ = ("_repository",)

    password_hasher: PasswordHasher = PasswordHasher(type=Type.ID)

    def __init__(self, repository: AuthRepository) -> None:
        self._repository = repository

    async def Authenticate(self, username: str, password: str) -> bool:
        user_auth = await self._repository.By(username)
        if user_auth is None or user_auth.username != username:
            return False
        return await asyncio.to_thread(
            self._VerifyPassword, password, user_auth.password
        )

    def _VerifyPassword(self, password: str, encoded: str) -> bool:
        if not encoded.startswith("$argon2id$"):
            return False
        try:
            return self.password_hasher.verify(encoded, password)
        except (InvalidHashError, VerificationError):
            return False
