#  Copyright (c) Kuba Szczodrzyński 2024-10-9.

import click
import cloup

from pynetkit import get_version
from pynetkit.cli.command import run_command
from pynetkit.cli.util.mce import mce

from .base import CONTEXT_SETTINGS, BaseCommandModule


@cloup.command(context_settings=CONTEXT_SETTINGS)
@click.argument("command", nargs=-1)
def cli(command: list[str]):
    from pynetkit.cli.command import COMMANDS

    if command:
        run_command(" ".join(command) + " --help")
    else:
        mce(f"§apynetkit CLI §8v{get_version()}§r\n")
        mce("§fCommands:§r")
        max_len = max(len(x) for x in COMMANDS)
        for name, (help_str, _) in sorted(COMMANDS.items()):
            padding = max_len - len(name)
            mce(f"  §e{name}§r{' ' * padding}  {help_str}")


COMMAND = BaseCommandModule(cli)
