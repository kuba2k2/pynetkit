#  Copyright (c) Kuba Szczodrzyński 2024-10-18.

import asyncio
from typing import Any, Generator, TypeVar

import click
from click import BaseCommand, Group
from cloup import Context, HelpFormatter, HelpTheme

from pynetkit.cli.config import Config

T = TypeVar("T")

CONTEXT_SETTINGS = Context.settings(
    help_option_names=[],
    formatter_settings=HelpFormatter.settings(
        theme=HelpTheme.dark(),
    ),
)


def async_command(func):
    def wrapper(*args, **kwargs):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        loop.run_until_complete(func(*args, **kwargs))

    wrapper.__name__ = func.__name__
    return wrapper


def index_option(
    cls: type,
    items: list[T],
    name: str,
    title: str = "item",
    required: bool = True,
):
    class IndexType(click.ParamType):
        name = "index"

        def convert(self, value: str, param, ctx):
            if required:
                return self._convert(value)
            else:
                try:
                    return self._convert(value)
                except (ValueError, TypeError):
                    return None

        @staticmethod
        def _convert(value: str):
            if isinstance(value, cls):
                return value
            if not isinstance(value, int) and not value.isnumeric():
                raise TypeError("Index value must be a number")
            index = int(value)
            if not items:
                raise ValueError(f"No {title} is created, use 'new' to add one")
            if not index:
                if len(items) == 1:
                    return items[0]
                else:
                    raise ValueError(f"More than one {title}, pass -@ to specify index")
            if (index - 1) not in range(len(items)):
                raise ValueError(f"No such {title}, valid indexes are 1..{len(items)}")
            return items[index - 1]

    return click.option(
        "-@",
        "--index",
        name,
        type=IndexType(),
        help=f"Index of the {title} (if more than one).",
        default=0,
    )


class BaseCommandModule:
    CLI: BaseCommand = None

    def __init__(self, cli: BaseCommand = None):
        if cli:
            self.CLI = cli
        self._add_help(self.CLI)

    def on_load(self) -> None:
        pass

    def _add_help(self, command: BaseCommand) -> None:
        click.option(
            "-h",
            "--help",
            is_flag=True,
            is_eager=True,
            expose_value=False,
            hidden=True,
            callback=self._help,
        )(command)
        if isinstance(command, Group):
            command.command(name="?", hidden=True)(click.pass_context(self._help))
            command.command(name="help", hidden=True)(click.pass_context(self._help))
            for command in command.commands.values():
                self._add_help(command)

    @staticmethod
    def _help(ctx: Context, _: Any = None, value: bool = True) -> None:
        if ctx.command.name in ["?", "help"]:
            ctx = ctx.parent
        if not value or ctx.resilient_parsing:
            return
        click.echo(ctx.get_help(), color=ctx.color)
        ctx.exit()

    def config_get(self) -> Config.Module:
        return Config.Module()

    def config_commands(self, config: Config.Module) -> Generator[str, None, None]:
        yield from ()
