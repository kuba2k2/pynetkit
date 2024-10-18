#  Copyright (c) Kuba Szczodrzyński 2024-10-9.

from pathlib import Path
from typing import Any

import click
from colorama import Fore
from prettytable import PrettyTable
from prettytable.colortable import ColorTable, Themes


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
        _, _, result = result.partition("\n")
        result = result.strip()
    click.echo(result)
