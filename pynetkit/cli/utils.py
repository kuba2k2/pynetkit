#  Copyright (c) Kuba Szczodrzyński 2024-10-9.

import re
from pathlib import Path
from typing import Any

import click
from colorama import Fore
from prettytable import PrettyTable
from prettytable.colortable import ColorTable, Themes

MC_REGEX = re.compile(r"\u00c2?(\u00a7[0-9a-fr])")
MC_COLORS = {
    "§0": Fore.BLACK,
    "§1": Fore.BLUE,
    "§2": Fore.GREEN,
    "§3": Fore.CYAN,
    "§4": Fore.RED,
    "§5": Fore.MAGENTA,
    "§6": Fore.YELLOW,
    "§7": Fore.WHITE,
    "§8": Fore.LIGHTBLACK_EX,
    "§9": Fore.LIGHTBLUE_EX,
    "§a": Fore.LIGHTGREEN_EX,
    "§b": Fore.LIGHTCYAN_EX,
    "§c": Fore.LIGHTRED_EX,
    "§d": Fore.LIGHTMAGENTA_EX,
    "§e": Fore.LIGHTYELLOW_EX,
    "§f": Fore.LIGHTWHITE_EX,
    "§r": Fore.RESET,
}


def mc(value: str) -> str:
    # "mc" means "multi-color", not Minecraft... why would you even think that?
    return re.sub(MC_REGEX, lambda m: MC_COLORS[m.group(1)], str(value))


def mce(value: str) -> None:
    # multi-color echo :)
    click.echo(mc(value))


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
    color: bool = True,
    header: list[str] = None,
) -> None:
    if header:
        field_names = header
    else:
        field_names = ["Key", "Value"]
    if color:
        table = ColorTable(field_names, theme=Themes.OCEAN_DEEP)
    else:
        table = PrettyTable(field_names)
    table.title = title
    table.header = bool(header)
    table.align = "l"
    for key, value in args:
        if key == "" and value == "":
            continue
        if color:
            # don't use color for values
            table.add_row([key, Fore.RESET + mc(value) + Fore.RESET])
        else:
            table.add_row([key, value])
    result = table.get_string()
    if no_top:
        _, _, result = result.partition("\n")
        result = result.strip()
    click.echo(result)
