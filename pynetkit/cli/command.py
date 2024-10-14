#  Copyright (c) Kuba Szczodrzyński 2024-10-10.

import shlex
from logging import error, exception

from pynetkit.cli.utils import import_module

COMMANDS = {
    "help": ("Get help.", "pynetkit/cli/commands/help.py"),
    "exit": ("Quit the program.", "pynetkit/cli/commands/exit.py"),
}
ALIASES = {
    "?": "help",
    "q": "exit",
    "quit": "exit",
}


def run_command(line: str):
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
        try:
            module = import_module(module)
        except Exception as e:
            exception("Module import failed", exc_info=e)
            return
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
    except Exception as e:
        exception("Command invocation failed", exc_info=e)
