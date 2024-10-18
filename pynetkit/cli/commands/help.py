#  Copyright (c) Kuba Szczodrzyński 2024-10-9.

import click
import cloup
from colorama import Fore

from pynetkit import get_version
from pynetkit.cli.command import run_command

from .base import CONTEXT_SETTINGS, BaseCommandModule


@cloup.command(context_settings=CONTEXT_SETTINGS)
@click.argument("command", nargs=-1)
def cli(command: list[str]):
    from pynetkit.cli.command import COMMANDS

    if command:
        run_command(" ".join(command) + " --help")
    else:
        click.secho(f"pynetkit CLI v{get_version()}\n", fg="bright_green")
        click.secho("Commands:", fg="bright_white")
        max_len = max(len(x) for x in COMMANDS)
        for name, (help_str, _) in sorted(COMMANDS.items()):
            padding = max_len - len(name)
            click.echo(
                f"  {Fore.LIGHTYELLOW_EX + name + Fore.RESET}"
                f"{' ' * padding}"
                f"  {help_str}"
            )


class CommandModule(BaseCommandModule):
    CLI = cli


COMMAND = CommandModule()
