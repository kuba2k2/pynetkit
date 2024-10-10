#  Copyright (c) Kuba Szczodrzyński 2024-10-9.

import os
from logging import DEBUG, INFO, exception

import click

from pynetkit.util.logging import VERBOSE, LoggingHandler

from .cli_simple import cli_simple

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

    cli_simple()


def cli():
    try:
        cli_entrypoint()
    except Exception as e:
        exception(None, exc_info=e)
        exit(1)


if __name__ == "__main__":
    cli()
