from __future__ import annotations

import asyncio

import pylibmc
from sanic.log import logger
from turso.lib_aio import Connection

from blackkeys.backends.broker import BrokerError
from blackkeys.backends.publishers.hydration import (
    HYDRATE_EVENTS_MESSAGE_NAME,
    HydrationPublisher,
    MakeHydrationPublisher,
)
from blackkeys.backends.publishers.signup import (
    MakeSignupPublisher,
    SignupPublisher,
)
from blackkeys.backends.services.events import (
    EventsService,
    MakeEventsService,
)
from blackkeys.backends.stores import cache as cache_store
from blackkeys.backends.stores.db import (
    DbStore,
    UserConflict,
    UserUnavailable,
)
from blackkeys.backends.stores.local import LocalCacheGet, LocalCacheSet
from blackkeys.core.conf import Settings


class AuthenticationUnavailable(Exception):
    pass


class SignupUnavailable(Exception):
    pass


class SignupConflict(Exception):
    pass


class AuthRepository:
    __slots__ = ("_cache", "_db", "_signup_publisher")

    def __init__(
        self,
        cache: pylibmc.ClientPool | None,
        signup_publisher: SignupPublisher | None,
        db: Connection | None = None,
    ) -> None:
        self._cache = cache
        self._signup_publisher = signup_publisher
        self._db = DbStore(db)

    def ValidUsername(self, username: str) -> bool:
        try:
            cache_store.UserAuthKey(username)
        except ValueError:
            return False
        return True

    async def Open(self, db: Connection | None = None) -> None:
        if db is not None:
            self._db.db = db
        if self._signup_publisher is None:
            return
        try:
            await self._signup_publisher.Connect()
        except BrokerError as error:
            logger.warning("signup queue unavailable at startup: %s", error)

    async def Close(self) -> None:
        self._db.db = None
        if self._signup_publisher is not None:
            await self._signup_publisher.Close()

    async def By(self, username: str) -> cache_store.CachedUserAuth | None:
        key = cache_store.UserAuthKey(username)
        local_value = LocalCacheGet(key)
        if isinstance(local_value, cache_store.CachedUserAuth):
            return local_value

        if self._cache is not None:
            try:
                cached = await asyncio.to_thread(
                    cache_store.ReadUserAuth,
                    self._cache,
                    username,
                )
            except pylibmc.Error as error:
                logger.warning("auth cache read failed: %s", error)
            else:
                if cached is not None:
                    LocalCacheSet(key, cached)
                    return cached

        user_auth = await self._ReadUser(username)
        if user_auth is None:
            return None

        if self._cache is not None:
            try:
                stored = await asyncio.to_thread(
                    cache_store.WriteUserAuth,
                    self._cache,
                    user_auth,
                )
                if not stored:
                    logger.warning("auth cache write failed for %s", username)
            except pylibmc.Error as error:
                logger.warning("auth cache write failed: %s", error)
        LocalCacheSet(key, user_auth)
        return user_auth

    async def CreateUser(
        self, username: str, password: str, email: str
    ) -> None:
        if self._db.db is None or self._signup_publisher is None:
            raise SignupUnavailable

        write_result, publish_result = await asyncio.gather(
            self._WriteUser(username, password, email),
            self._signup_publisher.Publish(username, password),
            return_exceptions=True,
        )
        if isinstance(write_result, SignupConflict):
            raise write_result
        if isinstance(write_result, Exception):
            if isinstance(publish_result, Exception):
                logger.warning("signup publish failed: %s", publish_result)
            if isinstance(write_result, SignupUnavailable):
                raise write_result
            logger.warning("signup insert failed: %s", write_result)
            raise SignupUnavailable from write_result
        if isinstance(publish_result, Exception):
            logger.warning("signup publish failed: %s", publish_result)
            raise SignupUnavailable from publish_result

    async def _WriteUser(
        self, username: str, password: str, email: str
    ) -> None:
        try:
            await self._db.CreateUser(username, password, email)
        except UserConflict as error:
            raise SignupConflict from error
        except UserUnavailable as error:
            if error.__cause__ is not None:
                logger.warning("signup insert failed: %s", error.__cause__)
            raise SignupUnavailable from error

    async def _ReadUser(
        self, username: str
    ) -> cache_store.CachedUserAuth | None:
        try:
            record = await self._db.ReadUser(username)
        except UserUnavailable as error:
            if error.__cause__ is not None:
                logger.warning(
                    "authentication query failed: %s", error.__cause__
                )
            raise AuthenticationUnavailable from error
        if record is None:
            return None
        return cache_store.CachedUserAuth(record.username, record.password)


class EventsRepository:
    __slots__ = ("_cache", "_hydration_publisher", "_service")

    def __init__(
        self,
        cache: pylibmc.ClientPool | None,
        hydration_publisher: HydrationPublisher | None,
        service: EventsService | None,
    ) -> None:
        self._cache = cache
        self._hydration_publisher = hydration_publisher
        self._service = service

    async def Open(self) -> None:
        if self._hydration_publisher is None:
            return
        try:
            await self._hydration_publisher.Connect()
        except BrokerError as error:
            logger.warning("hydration queue unavailable at startup: %s", error)

    async def Close(self) -> None:
        if self._hydration_publisher is not None:
            await self._hydration_publisher.Close()

    async def List(self) -> list | None:
        cached = LocalCacheGet(cache_store.EVENTS_LIST_CACHE_KEY)
        if isinstance(cached, list):
            return cached

        if self._cache is not None:
            try:
                value = await asyncio.to_thread(
                    cache_store.ReadEventsList, self._cache
                )
            except pylibmc.Error as error:
                logger.warning("events cache read failed: %s", error)
                value = None
            if value is not None:
                LocalCacheSet(cache_store.EVENTS_LIST_CACHE_KEY, value)
                return value

        if self._hydration_publisher is not None:
            try:
                await self._hydration_publisher.Publish(
                    HYDRATE_EVENTS_MESSAGE_NAME
                )
            except BrokerError as error:
                logger.warning("hydration publish failed: %s", error)

        if self._service is None:
            return None

        value = await self._service.List()
        if value is not None:
            LocalCacheSet(cache_store.EVENTS_LIST_CACHE_KEY, value)
        return value


def MakeEventsRepository(settings: Settings) -> EventsRepository:
    return EventsRepository(
        cache_store.MakeEventsCache(settings.cache_nodes),
        MakeHydrationPublisher(
            settings.mq_nodes,
            settings.mq_user,
            settings.mq_password,
            settings.mq_vhost,
            settings.mq_hydration_queue,
        ),
        MakeEventsService(settings.assets_host),
    )


def MakeAuthRepository(settings: Settings) -> AuthRepository:
    return AuthRepository(
        cache_store.MakeAuthCache(settings.cache_nodes),
        MakeSignupPublisher(
            settings.mq_nodes,
            settings.mq_user,
            settings.mq_password,
            settings.mq_vhost,
            settings.mq_signup_queue,
        ),
    )
