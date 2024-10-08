#  Copyright (c) Kuba Szczodrzyński 2023-9-11.

from .types import Request, RequestHandler


def request(
    method: str,
    path: str,
    *,
    host: str = None,
    query: dict = None,
    headers: dict = None,
):
    model = Request(method, path, host, query, headers)

    def attach(func: RequestHandler) -> RequestHandler:
        if not hasattr(func, "__requests__"):
            setattr(func, "__requests__", [])
        if model not in getattr(func, "__requests__"):
            getattr(func, "__requests__").append(model)
        return func

    return attach


def get(path: str, *, host: str = None, query: dict = None, headers: dict = None):
    return request("GET", path, host=host, query=query, headers=headers)


def post(path: str, *, host: str = None, query: dict = None, headers: dict = None):
    return request("POST", path, host=host, query=query, headers=headers)
