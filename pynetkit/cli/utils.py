#  Copyright (c) Kuba Szczodrzyński 2024-10-9.

import asyncio
import re
from pathlib import Path
from typing import Any, TypeVar

import click
from click import Context
from colorama import Fore
from prettytable import PrettyTable
from prettytable.colortable import ColorTable, Themes

T = TypeVar("T")


def import_module(filename: str) -> dict:
    ns = {}
    fn = Path(__file__).parents[2] / filename
    mp = filename.rpartition("/")[0].replace("/", ".")
    mn = fn.stem
    with open(fn) as f:
        code = compile(f.read(), fn, "exec")
        ns["__file__"] = fn
        ns["__name__"] = f"{mp}.{mn}"
        eval(code, ns, ns)
    return ns


def help_commands(cli):
    @cli.command(name="?", help="Show this message and exit.")
    @click.pass_obj
    def help1(ctx: Context):
        click.echo(ctx.get_help(), color=ctx.color)

    @cli.command(name="help", help="Show this message and exit.")
    @click.pass_obj
    def help2(ctx: Context):
        click.echo(ctx.get_help(), color=ctx.color)


def async_command(func):
    def wrapper(*args, **kwargs):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        loop.run_until_complete(func(*args, **kwargs))

    wrapper.__name__ = func.__name__
    return wrapper


def fetch_by_index(ctx: Context, items: list[T], title: str) -> T:
    index = getattr(ctx, "index", 0)
    if not items:
        raise ValueError(f"No {title} is created, use 'new' to add one")
    if len(items) == 1:
        return items[0]
    if not index:
        raise ValueError(f"More than one {title}, pass -@ to specify the index")
    if (index - 1) not in range(len(items)):
        raise ValueError(f"No such {title}, valid indexes are 1..{len(items)}")
    return items[index - 1]


def config_table(
    title: str,
    *args: tuple[Any, Any],
    no_top: bool = False,
    color: bool = False,
) -> None:
    if color:
        table = ColorTable(["Key", "Value"], theme=Themes.OCEAN_DEEP)
    else:
        table = PrettyTable(["Key", "Value"])
    table.title = title
    table.header = False
    table.align = "l"
    for key, value in args:
        if key == "" and value == "":
            continue
        if color:
            # don't use color for values
            table.add_row([key, Fore.RESET + str(value) + Fore.RESET])
        else:
            table.add_row([key, value])
    result = table.get_string()
    if no_top:
        result, _ = re.subn(r"\+-+\+", "", result, 1)
        result = result.strip()
    print(result)
