#  Copyright (c) Kuba Szczodrzyński 2024-10-9.

import os
import shlex
from logging import DEBUG, INFO, error, exception, info

import click

from pynetkit.util.logging import VERBOSE, LoggingHandler

from .utils import import_module

VERBOSITY_LEVEL = {
    0: INFO,
    1: DEBUG,
    2: VERBOSE,
}

COMMANDS = {
    "help": ("Get help", "pynetkit/cli/commands/help.py"),
    "exit": ("Quit the program", "pynetkit/cli/commands/exit.py"),
}
ALIASES = {
    "?": "help",
    "q": "exit",
    "quit": "exit",
}


@click.command(
    help="Reverse engineering utilities for several popular network protocols",
    context_settings=dict(help_option_names=["-h", "--help"]),
)
@click.option(
    "-v",
    "--verbose",
    help="Output debugging messages (repeat to output more)",
    count=True,
)
@click.option(
    "-T",
    "--traceback",
    help="Print complete exception traceback",
    is_flag=True,
)
@click.option(
    "-t",
    "--timed",
    help="Prepend log lines with timing info",
    is_flag=True,
)
@click.option(
    "-r",
    "--raw-log",
    help="Output logging messages with no additional styling",
    is_flag=True,
)
def cli_entrypoint(
    verbose: int,
    traceback: bool,
    timed: bool,
    raw_log: bool,
):
    if verbose == 0 and "LTCHIPTOOL_VERBOSE" in os.environ:
        verbose = int(os.environ["LTCHIPTOOL_VERBOSE"])
    logger = LoggingHandler.get()
    logger.level = VERBOSITY_LEVEL[min(verbose, 2)]
    logger.timed = timed
    logger.raw = raw_log
    logger.full_traceback = traceback

    info("pynetkit CLI")
    info("")
    info("Type 'help' or '?' to get some help.")

    while True:
        cli_loop()


def cli_loop():
    line: str = click.prompt("=> ", prompt_suffix="")
    # split command line
    cmd, _, args = line.strip().partition(" ")
    # discard empty lines
    if not cmd:
        return
    # map command aliases
    if cmd in ALIASES:
        cmd = ALIASES[cmd]
    # discard invalid commands
    if cmd not in COMMANDS:
        error(f"No such command: {cmd}")
        return
    # find command entrypoint
    help_str, module = COMMANDS[cmd]
    # import module if not imported yet
    if isinstance(module, str):
        module = import_module(module)
        COMMANDS[cmd] = (help_str, module)
    # make sure it has a CLI
    if "cli" not in module:
        error(f"Module '{cmd}' does not have a CLI")
        return
    # otherwise invoke the module entrypoint
    if isinstance(args, str):
        args = shlex.split(args)
    try:
        module["cli"].main(args=args or (), prog_name=cmd)
    except SystemExit as e:
        # prevent exiting unless requested explicitly
        if e.args and e.args[0] == module["cli"]:
            raise SystemExit()


def cli():
    try:
        cli_entrypoint()
    except Exception as e:
        exception(None, exc_info=e)
        exit(1)


if __name__ == "__main__":
    cli()
