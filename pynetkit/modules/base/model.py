#  Copyright (c) Kuba Szczodrzyński 2023-9-9.

from asyncio import Future
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Type

from .future import FutureMixin
from .utils import T, make_attr_dict


@dataclass
class BaseEvent:
    def __await__(self):
        setattr(self, "__used__", True)
        future = FutureMixin.make_future()
        make_attr_dict(type(self), "__subscribers__")[future] = self
        yield from future

    @classmethod
    def any(cls: Type[T]) -> Future[T]:
        future = FutureMixin.make_future()
        make_attr_dict(cls, "__subscribers__")[future] = cls
        return future

    def subscribe(self, handler: Callable[["BaseEvent"], None]) -> None:
        make_attr_dict(type(self), "__subscribers__")[handler] = self

    @classmethod
    def subscribe_all(cls, handler: Callable[["BaseEvent"], None]) -> None:
        make_attr_dict(cls, "__subscribers__")[handler] = cls

    @classmethod
    def unsubscribe(cls, handler: Callable[["BaseEvent"], None]) -> None:
        make_attr_dict(cls, "__subscribers__").pop(handler, None)

    def broadcast(self) -> None:
        from .event import EventMixin

        setattr(self, "__used__", True)
        subs: dict[Any | Future, type | object] = dict()
        # find subscribers of all superclasses
        cls = type(self)
        while cls.__base__:
            # |= will replace EventMixin keys (but the value doesn't matter anyway)
            # but will not remove any Futures, since they're unique
            # and their value (subscribed object) will be preserved
            subs |= getattr(cls, "__subscribers__", {})
            cls = cls.__base__
        # fill event queues and resolve futures
        futures = set()
        for sub, obj in subs.items():
            type_matches = isinstance(obj, type) and isinstance(self, obj)
            value_matches = self == obj
            if isinstance(sub, Future):
                # make sure the object matches
                if type_matches or value_matches:
                    FutureMixin.resolve_future(sub, self)
                    futures.add(sub)
            elif isinstance(sub, EventMixin):
                # the EventMixin handles dispatching the object, based on type
                sub.queue.put(self)
            elif callable(sub):
                # call simple event handlers
                if type_matches or value_matches:
                    sub(self)
            else:
                raise RuntimeError(f"Unknown event handler: {sub}")
        # remove all used futures
        cls = type(self)
        while cls.__base__:
            for future in futures:
                getattr(cls, "__subscribers__", {}).pop(future, None)
            cls = cls.__base__

    def __del__(self):
        if not hasattr(self, "__used__"):
            raise RuntimeError(f"Event '{self}' never broadcast nor awaited")


@dataclass
class MethodCallEvent:
    future: Future
    func: Callable[..., Awaitable[Any]]
    args: tuple
    kwargs: dict


@dataclass
class CoroutineCallEvent:
    coro: Awaitable[Any]
