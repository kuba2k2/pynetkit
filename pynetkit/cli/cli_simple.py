#  Copyright (c) Kuba Szczodrzyński 2024-10-10.

from logging import info

import click

from .command import run_command


def cli_simple():
    info("pynetkit CLI")
    info("")
    info("Type 'help' or '?' to get some help.")

    while True:
        line: str = click.prompt("=> ", prompt_suffix="")
        run_command(line)
