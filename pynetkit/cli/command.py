#  Copyright (c) Kuba Szczodrzyński 2024-10-10.

import os
import shlex
from logging import error, exception

from click import BaseCommand
from click.shell_completion import ShellComplete

from pynetkit.util.misc import import_module

from .commands.base import BaseCommandModule

COMMANDS: dict[str, tuple[str, str | BaseCommandModule]] = {
    # commands
    "help": ("Get help.", "pynetkit/cli/commands/help.py"),
    "exit": ("Quit the program.", "pynetkit/cli/commands/exit.py"),
    "config": ("Load/save module configuration.", "pynetkit/cli/commands/config.py"),
    # modules
    "dhcp": ("Manage the DHCP server.", "pynetkit/cli/commands/modules/dhcp.py"),
    "dns": ("Manage the DNS server.", "pynetkit/cli/commands/modules/dns.py"),
    "network": ("Manage the network card.", "pynetkit/cli/commands/modules/network.py"),
    "ntp": ("Manage the NTP server.", "pynetkit/cli/commands/modules/ntp.py"),
    "proxy": ("Manage the proxy server.", "pynetkit/cli/commands/modules/proxy.py"),
    "wifi": ("Manage the Wi-Fi adapters.", "pynetkit/cli/commands/modules/wifi.py"),
}
ALIASES = {
    "?": "help",
    "q": "exit",
    "quit": "exit",
    "conf": "config",
    "cfg": "config",
}


def get_module(cmd: str, no_import: bool = False) -> BaseCommandModule | None:
    # discard invalid commands
    if cmd not in COMMANDS:
        error(f"No such command: {cmd}")
        return None
    # find command entrypoint
    help_str, module = COMMANDS[cmd]
    # import module if not imported yet
    if isinstance(module, str):
        if no_import:
            return None
        try:
            module = import_module(module)["COMMAND"]
        except Exception as e:
            exception("Module import failed", exc_info=e)
            return None
        COMMANDS[cmd] = (help_str, module)
        module.on_load()
    return module


def get_command(line: str) -> tuple[BaseCommand | None, str, list[str]]:
    # split command line
    cmd, _, args = line.strip().partition(" ")
    # discard empty lines
    if not cmd:
        return None, cmd, []
    # map command aliases
    if cmd in ALIASES:
        cmd = ALIASES[cmd]
    # get command module
    module = get_module(cmd)
    if not module:
        return None, cmd, []
    # make sure it has a CLI
    if not module.CLI:
        error(f"Module '{cmd}' does not have a CLI")
        return None, cmd, []
    # otherwise process the command line arguments
    if isinstance(args, str):
        args = shlex.split(args, posix=os.name != "nt")
        if os.name == "nt":
            # shlex.split() in non-POSIX mode doesn't strip quotes
            for i, arg in enumerate(args):
                if arg and arg[0] == arg[-1] and arg[0] in "'\"":
                    arg = arg[1:-1]
                args[i] = arg
    else:
        args = []
    return module.CLI, cmd, args


def run_command(line: str) -> None:
    line, _, _ = line.partition("#")
    cli, cmd, args = get_command(line)
    if not cli:
        return
    try:
        cli.main(args=args, prog_name=cmd)
    except SystemExit as e:
        # prevent exiting unless requested explicitly
        if e.args and e.args[0] == cli:
            raise SystemExit()
    except Exception as e:
        exception("Command invocation failed", exc_info=e)


def run_completion(line: str) -> list[str] | None:
    line = line.lstrip()
    if " " not in line:
        # one word only, complete the command name, not its arguments
        names = list(COMMANDS.keys())
        if line in names:
            return []
        return [name for name in names if name.startswith(line)] or None
    cli, cmd, args = get_command(line)
    if not cli:
        # command does not exist
        return None
    # a valid command was found
    try:
        # remove the command name from line
        _, _, incomplete = line[len(cmd) :].rpartition(" ")
        # run completion
        comp = ShellComplete(cli=cli, ctx_args={}, prog_name=cmd, complete_var="")
        if args and args[-1] == incomplete:
            args = args[0:-1]
        completions = comp.get_completions(args, incomplete)
        if not incomplete:
            # also complete options, if cursor is at a whitespace
            completions += comp.get_completions(args, incomplete + "-")
        # skip non-plain items and ignored completions
        return [item.value for item in completions if item.type == "plain"]
    except SystemExit:
        pass
    except Exception as e:
        exception("Command completion failed", exc_info=e)
