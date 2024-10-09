#  Copyright (c) Kuba Szczodrzyński 2023-9-8.

import os
import sys
from subprocess import PIPE, Popen

from .event import EventMixin


class ModuleBase(EventMixin):
    PRE_RUN_CONFIG: list[str] = None

    def __setattr__(self, key, value):
        if (
            not self.PRE_RUN_CONFIG
            or key not in self.PRE_RUN_CONFIG
            or not self.is_started
        ):
            super().__setattr__(key, value)
            return
        raise RuntimeError(f"{type(self).__name__} must be stopped first")

    @staticmethod
    def is_windows() -> bool:
        return os.name == "nt"

    @staticmethod
    def is_linux() -> bool:
        return sys.platform == "linux"

    def command(self, *args: str) -> bytes:
        p = Popen(args=[*args], stdout=PIPE, stderr=PIPE)
        stdout, stderr = p.communicate()
        if p.wait() != 0:
            raise RuntimeError(
                f"Command {args} failed ({p.returncode}): {(stdout or stderr)}"
            )
        self.debug(f"Command {args} finished")
        return stdout
