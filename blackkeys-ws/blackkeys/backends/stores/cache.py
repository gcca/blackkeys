from __future__ import annotations

import hashlib
import json
import struct
import threading
from dataclasses import dataclass
from typing import Literal

import flatbuffers
import flatbuffers.util
import pylibmc

from blackkeys.schemas.UserAuth import (
    UserAuth,
    UserAuthAddPassword,
    UserAuthAddUsername,
    UserAuthEnd,
    UserAuthStart,
)

DEFAULT_REPLICATION = 1
AUTH_USER_KEY_PREFIX = "auth:user:"
AUTH_CACHE_POOL_SIZE = 4
USER_AUTH_CACHE_TTL_SECONDS = 210
USER_AUTH_IDENTIFIER = b"BKUA"
EVENTS_LIST_CACHE_KEY = "blackkeys-events-list"
EVENTS_CACHE_POOL_SIZE = 4


@dataclass(frozen=True, slots=True)
class CachedUserAuth:
    username: str
    password: str


def UserAuthKey(username: str) -> str:
    if not username:
        raise ValueError("username must not be empty")

    key = f"{AUTH_USER_KEY_PREFIX}{username}"
    encoded_key = key.encode()
    if any(byte <= 32 or byte == 127 for byte in encoded_key):
        raise ValueError("username contains unsupported characters")
    if len(encoded_key) > 250:
        raise ValueError("username is too long")
    return key


def EncodeUserAuth(username: str, password: str) -> bytes:
    UserAuthKey(username)
    if not password:
        raise ValueError("password must not be empty")

    builder = flatbuffers.Builder(256)
    username_offset = builder.CreateString(username)
    password_offset = builder.CreateString(password)
    UserAuthStart(builder)
    UserAuthAddUsername(builder, username_offset)
    UserAuthAddPassword(builder, password_offset)
    root = UserAuthEnd(builder)
    builder.Finish(root, file_identifier=USER_AUTH_IDENTIFIER)
    return bytes(builder.Output())


def DecodeUserAuth(
    value: bytes | bytearray | memoryview,
) -> CachedUserAuth | None:
    buffer = bytes(value)
    try:
        if not flatbuffers.util.BufferHasIdentifier(
            buffer, 0, USER_AUTH_IDENTIFIER
        ):
            return None
        user_auth = UserAuth.GetRootAs(buffer)
        username_value = user_auth.Username()
        password_value = user_auth.Password()
        if username_value is None or password_value is None:
            return None
        username = username_value.decode()
        password = password_value.decode()
    except (IndexError, TypeError, UnicodeDecodeError, struct.error):
        return None

    if not username or not password:
        return None
    return CachedUserAuth(username, password)


def MakeCachePool(
    nodes: tuple[str, ...],
    pool_size: int,
    replication: int = DEFAULT_REPLICATION,
) -> pylibmc.ClientPool | None:
    if not nodes:
        return None
    if pool_size <= 0:
        raise ValueError("pool_size must be greater than zero")

    client = pylibmc.Client(
        list(nodes),
        binary=True,
        behaviors={
            "ketama": True,
            "num_replicas": replication,
        },
    )
    pool = pylibmc.ClientPool(client, pool_size)
    pool.nodes = nodes
    pool.replication = replication
    pool.node_clients = {}
    pool.node_locks = {}
    for node in nodes:
        if node in pool.node_clients:
            continue
        pool.node_clients[node] = pylibmc.Client(
            [node], binary=True, behaviors={}
        )
        pool.node_locks[node] = threading.Lock()
    return pool


def _ReplicaNodes(
    nodes: tuple[str, ...], start: int, replication: int
) -> tuple[str, ...]:
    count = len(nodes)
    if count == 0:
        return ()
    chosen: list[str] = []
    seen: set[str] = set()
    for offset in range(replication + 1):
        node = nodes[(start + offset) % count]
        if node in seen:
            continue
        seen.add(node)
        chosen.append(node)
    return tuple(chosen)


def _SetReplicated(
    cache: pylibmc.ClientPool, key: str, value: bytes, **kwargs: object
) -> bool:
    with cache.reserve(block=True) as client:
        start = client.hash(key)
    stored = True
    for node in _ReplicaNodes(cache.nodes, start, cache.replication):
        with cache.node_locks[node]:
            if not cache.node_clients[node].set(key, value, **kwargs):
                stored = False
    return stored


def MakeAuthCache(
    nodes: tuple[str, ...],
    pool_size: int = AUTH_CACHE_POOL_SIZE,
    replication: int = DEFAULT_REPLICATION,
) -> pylibmc.ClientPool | None:
    return MakeCachePool(nodes, pool_size, replication)


def ReadUserAuth(
    cache: pylibmc.ClientPool, username: str
) -> CachedUserAuth | None:
    with cache.reserve(block=True) as client:
        value = client.get(UserAuthKey(username))
    if value is None or not isinstance(value, (bytes, bytearray, memoryview)):
        return None
    return DecodeUserAuth(value)


def WriteUserAuth(cache: pylibmc.ClientPool, user_auth: CachedUserAuth) -> bool:
    return _SetReplicated(
        cache,
        UserAuthKey(user_auth.username),
        EncodeUserAuth(user_auth.username, user_auth.password),
        time=USER_AUTH_CACHE_TTL_SECONDS,
    )


def MakeEventsCache(
    nodes: tuple[str, ...],
    pool_size: int = EVENTS_CACHE_POOL_SIZE,
    replication: int = DEFAULT_REPLICATION,
) -> pylibmc.ClientPool | None:
    return MakeCachePool(nodes, pool_size, replication)


def ReadEventsList(cache: pylibmc.ClientPool) -> list | None:
    with cache.reserve(block=True) as client:
        value = client.get(EVENTS_LIST_CACHE_KEY)
    if value is None or not isinstance(value, (bytes, bytearray, memoryview)):
        return None
    try:
        decoded = json.loads(bytes(value))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, list):
        return None
    return decoded


BRANDS_LIST_CACHE_KEY = "blackkeys-brands-list"
BRANDS_CACHE_POOL_SIZE = 4
BRANDS_LIST_CACHE_TTL_SECONDS = 4500
BRAND_IMAGE_CACHE_KEY_PREFIX = "blackkeys-brand-image:"
BRAND_IMAGE_CACHE_MAGIC = b"BKBI"
BRAND_IMAGE_CACHE_HEADER = struct.Struct(">4sH")
BrandImageKind = Literal["logo", "picture"]


@dataclass(frozen=True, slots=True)
class CachedBrandImage:
    data: bytes
    content_type: str


def BrandImageKey(kind: BrandImageKind, name: str) -> str:
    if kind not in ("logo", "picture"):
        raise ValueError("brand image kind must be logo or picture")
    digest = hashlib.sha256(name.encode(), usedforsecurity=False).hexdigest()
    return f"{BRAND_IMAGE_CACHE_KEY_PREFIX}{kind}:{digest}"


def EncodeBrandImage(image: CachedBrandImage) -> bytes:
    content_type = image.content_type.encode()
    if not content_type:
        raise ValueError("brand image content type must not be empty")
    if len(content_type) > 65535:
        raise ValueError("brand image content type is too long")
    if not image.data:
        raise ValueError("brand image data must not be empty")
    return (
        BRAND_IMAGE_CACHE_HEADER.pack(
            BRAND_IMAGE_CACHE_MAGIC, len(content_type)
        )
        + content_type
        + image.data
    )


def DecodeBrandImage(value: object) -> CachedBrandImage | None:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        return None
    buffer = bytes(value)
    if len(buffer) < BRAND_IMAGE_CACHE_HEADER.size:
        return None
    try:
        magic, content_type_length = BRAND_IMAGE_CACHE_HEADER.unpack_from(
            buffer
        )
    except struct.error:
        return None
    if magic != BRAND_IMAGE_CACHE_MAGIC or content_type_length == 0:
        return None
    data_offset = BRAND_IMAGE_CACHE_HEADER.size + content_type_length
    if data_offset >= len(buffer):
        return None
    try:
        content_type = buffer[
            BRAND_IMAGE_CACHE_HEADER.size : data_offset
        ].decode()
    except UnicodeDecodeError:
        return None
    if not content_type:
        return None
    return CachedBrandImage(buffer[data_offset:], content_type)


def MakeBrandsCache(
    nodes: tuple[str, ...],
    pool_size: int = BRANDS_CACHE_POOL_SIZE,
    replication: int = DEFAULT_REPLICATION,
) -> pylibmc.ClientPool | None:
    return MakeCachePool(nodes, pool_size, replication)


def ReadBrandsList(cache: pylibmc.ClientPool) -> list | None:
    with cache.reserve(block=True) as client:
        value = client.get(BRANDS_LIST_CACHE_KEY)
    if value is None or not isinstance(value, (bytes, bytearray, memoryview)):
        return None
    try:
        decoded = json.loads(bytes(value))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(decoded, list):
        return None
    return decoded


def ReadBrandImage(
    cache: pylibmc.ClientPool, kind: BrandImageKind, name: str
) -> CachedBrandImage | None:
    with cache.reserve(block=True) as client:
        value = client.get(BrandImageKey(kind, name))
    if value is None or not isinstance(value, (bytes, bytearray, memoryview)):
        return None
    return DecodeBrandImage(value)


def WriteBrandsList(cache: pylibmc.ClientPool, brands: list) -> bool:
    return _SetReplicated(
        cache,
        BRANDS_LIST_CACHE_KEY,
        json.dumps(brands).encode(),
        time=BRANDS_LIST_CACHE_TTL_SECONDS,
    )


def WriteBrandImage(
    cache: pylibmc.ClientPool,
    kind: BrandImageKind,
    name: str,
    image: CachedBrandImage,
    ttl_seconds: int,
) -> bool:
    return _SetReplicated(
        cache,
        BrandImageKey(kind, name),
        EncodeBrandImage(image),
        time=ttl_seconds,
    )
