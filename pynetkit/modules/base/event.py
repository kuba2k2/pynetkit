#  Copyright (c) Kuba Szczodrzyński 2023-9-8.

import asyncio
from asyncio import AbstractEventLoop, Future
from queue import Queue
from threading import Thread, current_thread
from typing import Any, Awaitable, Generator

from .future import FutureMixin
from .logger import LoggerMixin
from .model import BaseEvent, CoroutineCallEvent, MethodCallEvent
from .utils import EventHandler, T, make_attr_dict


class EventMixin(FutureMixin, LoggerMixin):
    queue: Queue[MethodCallEvent | CoroutineCallEvent | BaseEvent | Future]
    thread: Thread | None = None
    should_run: bool = False
    in_event_queue: bool = False

    def __init__(self):
        super().__init__()
        self.queue = Queue()

    @property
    def is_started(self) -> bool:
        return bool(self.thread)

    def entrypoint(self, future: Future = None) -> None:
        self.should_run = True
        thread = current_thread()
        thread.name = thread.name.replace("(entrypoint)", "").strip()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        if future:
            self.resolve_future(future)  # notify that the thread is running
        try:
            loop.run_until_complete(self.run())
        except Exception as e:
            if self.should_run:
                self.exception("Thread raised exception", exc_info=e)

        self.verbose("Finished run()")
        self.thread = None  # clear thread created in start()
        loop.run_until_complete(self.cleanup())
        if self.in_event_queue:
            # stop the event loop if in another thread
            loop.run_until_complete(self.event_loop_thread_stop())

    async def start(self) -> None:
        if self.is_started:
            raise RuntimeError(f"{type(self).__name__} is already started")
        self.verbose(f"Starting")
        future = self.make_future()
        self.thread = Thread(
            target=self.entrypoint,
            args=[future],
            daemon=True,
        )
        self.thread.start()
        await future  # wait until it starts

    async def stop(self) -> None:
        self.verbose(f"Stopping (request)")
        self.should_run = False
        await self.event_loop_thread_stop()
        if self.thread and self.thread is not current_thread():
            self.thread.join()

    async def run(self) -> None:
        # default implementation - simple event loop
        self.register_subscribers()
        await self.event_loop()

    async def cleanup(self) -> None:
        self.unregister_subscribers()

    async def event_loop(self, loop: AbstractEventLoop = None) -> None:
        while self.should_run:
            self.in_event_queue = True
            event = self.queue.get()
            self.in_event_queue = False
            match event:
                case Future():
                    self.resolve_future(event)
                    break
                case MethodCallEvent(future, func, args, kwargs):
                    try:
                        result = await func(self, *args, **kwargs)
                        self.resolve_future(future, result)
                    except Exception as e:
                        self.exception(f"Method call raised exception", exc_info=e)
                        self.resolve_future(future, None)
                case CoroutineCallEvent(coro):
                    await coro
                case BaseEvent():
                    for func, obj in self._iter_event_handlers():
                        # dispatch to instance methods
                        # if event type or entire value matches
                        type_matches = isinstance(obj, type) and isinstance(event, obj)
                        value_matches = event == obj
                        if type_matches or value_matches:
                            if loop:
                                asyncio.run_coroutine_threadsafe(
                                    func(self, event),
                                    loop,
                                )
                            else:
                                await func(self, event)

    async def event_loop_thread_start(self) -> None:
        loop = asyncio.get_running_loop()
        future = self.make_future()

        def event_loop():
            self.resolve_future(future)
            worker_loop = asyncio.new_event_loop()
            worker_loop.run_until_complete(self.event_loop(loop))

        Thread(target=event_loop).start()
        await future

    async def event_loop_thread_stop(self) -> None:
        if self.in_event_queue:
            # unblock the message loop
            future = self.make_future()
            self.queue.put(future)
            await future

    def _iter_event_handlers(self) -> Generator[tuple[Any, type | object], Any, None]:
        for name, func in type(self).__dict__.items():
            if not hasattr(func, "__events__"):
                continue
            for obj in getattr(func, "__events__"):
                yield func, obj

    def register_subscribers(self) -> None:
        for _, obj in self._iter_event_handlers():
            cls = obj if isinstance(obj, type) else obj.__class__
            make_attr_dict(cls, "__subscribers__")[self] = obj

    def unregister_subscribers(self) -> None:
        for _, obj in self._iter_event_handlers():
            cls = obj if isinstance(obj, type) else obj.__class__
            try:
                make_attr_dict(cls, "__subscribers__").pop(self, None)
            except KeyError:
                pass

    def call_coroutine(self, coro: Awaitable[Any]) -> None:
        self.queue.put(CoroutineCallEvent(coro))

    async def call_threaded(self, coro: Awaitable[Any]) -> Future[bool]:
        start_future = self.make_future()
        end_future = self.make_future()

        def event_loop():
            self.resolve_future(start_future)
            worker_loop = asyncio.new_event_loop()
            worker_loop.run_until_complete(coro)
            self.resolve_future(end_future)

        Thread(target=event_loop).start()
        await start_future
        return end_future


def subscribe(obj: type | object):
    def decorator(func: EventHandler) -> EventHandler:
        if not hasattr(func, "__events__"):
            setattr(func, "__events__", set())
        getattr(func, "__events__").add(obj)
        return func

    return decorator


def module_thread(func: T) -> T:
    async def inner(self: EventMixin, *args, **kwargs):
        if not self.thread or current_thread() == self.thread:
            return await func(self, *args, **kwargs)
        future = self.make_future()
        self.queue.put(MethodCallEvent(future, func, args, kwargs))
        return await future

    return inner
