#  Copyright (c) Kuba Szczodrzyński 2024-10-9.

import click


@click.command()
def cli():
    from pynetkit.cli.command import COMMANDS

    max_len = max(len(x) for x in COMMANDS)
    for name, (help_str, _) in sorted(COMMANDS.items()):
        padding = max_len - len(name)
        print(f"{name}{' ' * padding}  {help_str}")
