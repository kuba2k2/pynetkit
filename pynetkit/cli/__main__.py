#  Copyright (c) Kuba Szczodrzyński 2024-10-9.

import colorama

# run and then hijack init() so that streams don't get re-wrapped
colorama.init()
colorama.init = lambda *_, **__: None

import os
import sys
from logging import DEBUG, INFO, exception

import click

from pynetkit.util.logging import VERBOSE, LoggingHandler

from .eventlog import event_log_subscribe

VERBOSITY_LEVEL = {
    0: INFO,
    1: DEBUG,
    2: VERBOSE,
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
@click.option(
    "-s",
    "--simple",
    help="Use the simple CLI (instead of curses-based TUI)",
    is_flag=True,
)
@click.option(
    "-P",
    "--pycharm-debug",
    help="Connect to a PyCharm/IntelliJ debugger on 127.0.0.1:1234",
    is_flag=True,
)
def cli_entrypoint(
    verbose: int,
    traceback: bool,
    timed: bool,
    raw_log: bool,
    simple: bool,
    pycharm_debug: bool,
):
    if verbose == 0 and "LTCHIPTOOL_VERBOSE" in os.environ:
        verbose = int(os.environ["LTCHIPTOOL_VERBOSE"])
    logger = LoggingHandler.get()
    logger.level = VERBOSITY_LEVEL[min(verbose, 2)]
    logger.timed = timed
    logger.raw = raw_log
    logger.full_traceback = traceback

    event_log_subscribe()

    if pycharm_debug:
        import pydevd_pycharm

        pydevd_pycharm.settrace("127.0.0.1", port=1234, suspend=False)

    if sys.stdout.isatty() and not simple:
        from .cli_curses import cli_curses

        cli_curses()
    else:
        from .cli_simple import cli_simple

        cli_simple()


def cli():
    try:
        cli_entrypoint()
    except Exception as e:
        exception(None, exc_info=e)
        exit(1)


if __name__ == "__main__":
    cli()
