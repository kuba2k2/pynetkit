#  Copyright (c) Kuba Szczodrzyński 2024-10-18.

from logging import error
from pathlib import Path
from typing import Generator

import click
import cloup
from click import Context

from pynetkit.cli.config import Config
from pynetkit.cli.util.mce import config_table, mce, mce_yaml
from pynetkit.util.misc import filter_dict
from pynetkit.util.yml import yaml_dump

from .base import CONTEXT_SETTINGS, BaseCommandModule

PathType = cloup.file_path(readable=True, writable=True, resolve_path=True)


def iter_modules(*names: str) -> Generator[tuple[str, BaseCommandModule], None, None]:
    from pynetkit.cli.command import COMMANDS

    found = False
    for name, (_, module) in sorted(COMMANDS.items()):
        if isinstance(module, str):
            continue
        if ".modules." not in type(module).__module__:
            continue
        if names and name not in names:
            continue
        found = True
        yield name, module
    if not found:
        if names:
            error("No module by this name(s) has been loaded")
        else:
            error("No modules have been loaded so far")


@cloup.group(
    name="config",
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@click.pass_context
def cli(ctx: Context):
    if ctx.invoked_subcommand:
        return

    from pynetkit.cli.command import COMMANDS

    config = Config.get()
    config.update()

    if config.meta.name:
        mce(config.meta.to_mce())
    else:
        mce("\n§cMetadata is not set. Please set it using §dconfig meta§r.")

    if not config.path:
        mce("\n§cCurrent config is not saved to a file.§r\n")
    elif not config.saved:
        mce(f"\n§eCurrent config has changed since loading from: §d{config.path}§r\n")
    else:
        mce(f"\n§aCurrent config is saved to: §d{config.path}§r\n")

    mce(
        """§fCommands:§r
  §econfig meta §dname §cversion §aauthor§r  Set config metadata before saving.
  §econfig save§r                      Overwrite the loaded config file.
  §econfig save §dpath§r                 Save the config to §dpath§r.
  §econfig save §dpath§r §cmodule§r...       Save §cmodule§r(s) config to §dpath§r.
  §econfig load§r                      Reload the loaded config file.
  §econfig load §dpath§r                 Replace the current config with §dpath§r.
  §econfig load §dpath §cmodule§r...       Load only §cmodule§r(s) config from §dpath§r.
  §econfig dump§r                      Print the current complete config.
  §econfig dump §cmodule§r...            Print configuration of §cmodule§r(s).
  §econfig commands§r                  Show commands that make the current config.
  §econfig commands §cmodule§r...        Show commands for §cmodule§r(s).
  §econfig reset §cmodule§r...           Reset one or more §cmodule§r(s) (or 'all').
    """
    )

    args = []
    for name, (_, module) in sorted(COMMANDS.items()):
        if isinstance(module, str):
            if "/modules/" in module:
                args.append((name, "§8Unloaded"))
            continue
        if ".modules." not in type(module).__module__:
            continue
        args.append((name, "§aLoaded"))
    config_table("Module status", *args)

    mce("\nSaving the config will only save the loaded modules.")
    mce("Loading the config will load all modules specified in the config file.")


@cloup.command(help="Set config metadata.")
@cloup.argument("name", help="Name of the config.")
@cloup.argument("version", help="Version of the config (please use SemVer).")
@cloup.argument("author", help="Your name or nickname.")
def meta(name: str, version: str, author: str):
    config = Config.get()
    config.meta.name = name
    config.meta.version = version
    config.meta.author = author
    config.update()
    mce(config.meta.to_mce())


@cloup.command(help="Print the current complete config.")
@cloup.argument("modules", required=False, nargs=-1, help="Module(s) to include.")
def dump(modules: tuple[str]):
    config = Config.get()
    config.update()
    if not modules:
        if config.meta.name:
            mce(config.meta.to_mce() + "\n")
        mce_yaml(yaml_dump(config.dump()))
        return
    for name, module in filter_dict(dict(config.modules), modules).items():
        if not module.config:
            mce(f"\nModule §d{name}§r does not export configuration.")
        else:
            mce(f"\n§fConfiguration of the module §d{name}§r:")
            mce_yaml(yaml_dump(dict(config=module.config)))
        for script, commands in module.scripts.items():
            mce(f"§fScript §d{script}§f commands of the module §d{name}§r:")
            mce("\n".join(f"- §b{c.command}§r" for c in commands))


@cloup.command(help="Save the current config to a file.")
@cloup.argument("path", type=PathType, required=False, help="Path to write to.")
@cloup.argument("modules", required=False, nargs=-1, help="Module(s) to include.")
def save(path: Path | None, modules: tuple[str]):
    config = Config.get()
    config.update()
    previous_path = config.path
    config.save(path, *modules)
    if config.meta.name:
        mce(config.meta.to_mce())
    if not path:
        if previous_path:
            mce(f"§aReplaced configuration in the file §d{config.path}§r.")
        else:
            mce(f"§aCreated a new configuration file §d{config.path}§r.")
    else:
        mce(f"§aConfiguration saved as §d{config.path}§r.")


@cloup.command(help="Load the config from a file, replacing the current one.")
@cloup.argument("path", type=PathType, required=False, help="Path to load from.")
@cloup.argument("modules", required=False, nargs=-1, help="Module(s) to include.")
def load(path: Path | None, modules: tuple[str]):
    config = Config.get()
    config.update()
    previous_path = config.path
    config.load(path, *modules)
    if config.meta.name:
        mce(config.meta.to_mce())
    if not path and previous_path:
        mce(f"§a\nReloaded configuration file §d{config.path}§r.")
    elif config.path:
        mce(f"§a\nConfiguration loaded from §d{config.path}§r.")


@cloup.command(help="Show commands that make the current config.")
@cloup.argument("modules", required=False, nargs=-1, help="Module(s) to include.")
def commands(modules: tuple[str]):
    from pynetkit.cli.command import get_module

    config = Config.get()
    config.update()
    if config.meta.name:
        mce(config.meta.to_mce())

    mce("§8# Commands from §dpreload§8 script§r")
    for command in config.get_script("preload", *modules):
        mce(f"§3=> {command}§r")

    for name, module in filter_dict(dict(config.modules), modules).items():
        if not module.config:
            mce(f"§8# Module §d{name}§8 does not export configuration§r")
            continue
        mce(f"§8# Commands from module §d{name}§r")
        module_cls = get_module(name, no_import=True)
        if not module_cls:
            mce(f"§8# Module §d{name}§8 is not loaded yet§r")
            continue
        for command in module_cls.config_commands(module):
            mce(f"§3=> {command}§r")

    mce("§8# Commands from §dload§8 script§r")
    for command in config.get_script("load", *modules):
        mce(f"§3=> {command}§r")

    mce("§8# Commands from §dunload§8 script§r")
    for command in config.get_script("unload", *modules, reverse=True):
        mce(f"§3=> {command}§r")


@cloup.command(help="Reset one or more modules to their default config.")
@cloup.argument("modules", required=True, nargs=-1, help="Module(s) to include.")
def reset(modules: tuple[str]):
    config = Config.get()
    config.update()
    if "all" not in modules:
        config.unload(*modules)
    else:
        config.reset()


cli.section("Configuration management", meta, reset)
cli.section("File operations", save, load)
cli.section("Inspection", dump, commands)
COMMAND = BaseCommandModule(cli)
