#  Copyright (c) Kuba Szczodrzyński 2023-9-8.

import asyncio
from asyncio import Future
from typing import Any


class FutureMixin:
    @staticmethod
    def make_future() -> Future[bool]:
        return asyncio.get_running_loop().create_future()

    @staticmethod
    def resolve_future(future: Future, result: Any = None) -> None:
        async def resolve():
            future.set_result(result)

        asyncio.run_coroutine_threadsafe(resolve(), future.get_loop())

    @staticmethod
    def reject_future(future: Future, error: Any = None) -> None:
        async def resolve():
            future.set_exception(error)

        asyncio.run_coroutine_threadsafe(resolve(), future.get_loop())
