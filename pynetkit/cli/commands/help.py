#  Copyright (c) Kuba Szczodrzyński 2024-10-9.

import click

from pynetkit.cli.command import run_command


@click.command()
@click.argument("command", nargs=-1)
def cli(command: list[str]):
    from pynetkit.cli.command import COMMANDS

    if command:
        run_command(" ".join(command) + " --help")
    else:
        print("Commands:")
        max_len = max(len(x) for x in COMMANDS)
        for name, (help_str, _) in sorted(COMMANDS.items()):
            padding = max_len - len(name)
            print(f"  {name}{' ' * padding}  {help_str}")
