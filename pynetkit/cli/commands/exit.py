#  Copyright (c) Kuba Szczodrzyński 2024-10-9.

import cloup

from .base import CONTEXT_SETTINGS, BaseCommandModule


@cloup.command(context_settings=CONTEXT_SETTINGS)
def cli():
    raise SystemExit(cli)


COMMAND = BaseCommandModule(cli)
