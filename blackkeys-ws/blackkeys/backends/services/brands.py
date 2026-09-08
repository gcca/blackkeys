from __future__ import annotations

import grpc.aio
from google.protobuf.json_format import MessageToDict
from sanic.log import logger

from blackkeys.gen.v1 import messages_pb2, service_pb2_grpc
from blackkeys.monitor import NotifyEvent

ASSETS_TIMEOUT_SECONDS = 5.0


class BrandImageNotFound(Exception):
    pass


def BrandsFromResponse(response: messages_pb2.ListResponse) -> list | None:
    payload = MessageToDict(
        response,
        always_print_fields_with_no_presence=True,
    )
    brands = payload.get("brands")
    if not isinstance(brands, list):
        return None
    return brands


class BrandsService:
    __slots__ = ("_target", "_channel", "_stub")

    def __init__(self, target: str) -> None:
        if not target:
            raise ValueError("target must not be empty")
        self._target = target
        self._channel = None
        self._stub = None

    async def Open(self) -> None:
        if self._channel is not None:
            return
        self._channel = grpc.aio.insecure_channel(self._target)
        self._stub = service_pb2_grpc.BrandsStub(self._channel)

    async def Close(self) -> None:
        if self._channel is None:
            return
        await self._channel.close()
        self._channel = None
        self._stub = None

    async def List(self) -> list | None:
        if self._stub is None:
            await self.Open()
        try:
            response = await self._stub.List(
                messages_pb2.ListRequest(),
                timeout=ASSETS_TIMEOUT_SECONDS,
            )
        except grpc.aio.AioRpcError as error:
            logger.warning("assets brands request failed: %s", error)
            NotifyEvent(
                f"brands list request failed: target={self._target} "
                f"code={error.code()} details={error.details()}",
                level="error",
            )
            return None
        return BrandsFromResponse(response)

    async def Logo(self, name: str) -> tuple[bytes, str] | None:
        return await self._Image("Logo", name)

    async def Picture(self, name: str) -> tuple[bytes, str] | None:
        return await self._Image("Picture", name)

    async def _Image(self, rpc: str, name: str) -> tuple[bytes, str] | None:
        if self._stub is None:
            await self.Open()
        try:
            response = await getattr(self._stub, rpc)(
                messages_pb2.ImageRequest(name=name),
                timeout=ASSETS_TIMEOUT_SECONDS,
            )
        except grpc.aio.AioRpcError as error:
            if error.code() == grpc.StatusCode.NOT_FOUND:
                raise BrandImageNotFound(name) from error
            logger.warning(
                "assets brand %s request failed: %s", rpc.lower(), error
            )
            NotifyEvent(
                f"brand {rpc.lower()} request failed: target={self._target} "
                f"name={name} code={error.code()} details={error.details()}",
                level="error",
            )
            return None
        return response.data, response.content_type


def MakeBrandsService(target: str | None) -> BrandsService | None:
    if not target:
        return None
    return BrandsService(target)
