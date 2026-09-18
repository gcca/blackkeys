from __future__ import annotations

import grpc.aio
from google.protobuf.json_format import MessageToDict
from sanic.log import logger

from blackkeys.gen.v1 import messages_pb2, service_pb2_grpc
from blackkeys.monitor import NotifyEvent

ASSETS_TIMEOUT_SECONDS = 5.0


def StoresFromResponse(response: messages_pb2.ListResponse) -> list | None:
    payload = MessageToDict(
        response,
        always_print_fields_with_no_presence=True,
    )
    stores = payload.get("stores")
    if not isinstance(stores, list):
        return None
    return stores


class StoresService:
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
        self._stub = service_pb2_grpc.StoresStub(self._channel)

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
            logger.warning("assets stores request failed: %s", error)
            NotifyEvent(
                f"stores list request failed: target={self._target} "
                f"code={error.code()} details={error.details()}",
                level="error",
            )
            return None
        return StoresFromResponse(response)


def MakeStoresService(target: str | None) -> StoresService | None:
    if not target:
        return None
    return StoresService(target)
