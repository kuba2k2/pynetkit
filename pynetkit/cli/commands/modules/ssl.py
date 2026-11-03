#  Copyright (c) Kuba Szczodrzyński 2026-11-2.

from logging import error
from pathlib import Path

import click
import cloup
from click import Context
from prettytable.colortable import ColorTable, Themes

from pynetkit.cli.commands.base import (
    CONTEXT_SETTINGS,
    BaseCommandModule,
)
from pynetkit.cli.util.mce import mc, mce
from pynetkit.modules.ssl import SslModule

ssl = SslModule()


@cloup.group(
    name="ssl",
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=True,
)
@click.pass_context
def cli(ctx: Context):
    if ctx.invoked_subcommand:
        return

    table = ColorTable(
        [" ", "Subject name(s)", "Issuer", "Usage"],
        theme=Themes.OCEAN_DEEP,
    )
    table.title = "SSL certificate store"
    table.align = "l"

    for idx, entry in enumerate(ssl.cert_db):
        usage = "\n".join(sorted(entry.usage))
        match (bool(entry.key), entry.is_ca):
            case (False, False):
                usage = "§cMissing private key§r"
            case (False, True):
                usage = "§8Chain only, no private key§r"
            case (True, False):
                title = "§2Certificate" if entry.paths else "§8Generated"
                usage = f"{title} for:§r\n" + (usage or "§8(not used yet)§r")
            case (True, True):
                usage = "§2Authority for:§r\n" + (usage or "§8(not used yet)§r")
        table.add_row(
            [
                idx + 1,
                "\n".join(entry.subject_names),
                mc(
                    f"§2{entry.issuer_cn}§r"
                    if ssl.get_issuer(entry)
                    else f"§4{entry.issuer_cn}§r"
                ),
                mc(usage),
            ]
        )

    click.echo(table.get_string())


@cloup.command(help="Import certificate/private key files.", name="import")
@cloup.argument(
    "paths",
    type=click.Path(exists=True, path_type=Path),
    nargs=-1,
    required=True,
    help="Paths to files (PEM-formatted) or directories (with *.pem files).",
)
def import_(paths: tuple[Path]):
    cert_count, key_count = ssl.import_files(*paths)
    mce(f"§fImported §d{cert_count}§f certificates and §d{key_count}§f private keys§r")


@cloup.command(help="Delete a certificate from the database.")
@cloup.argument("index", type=int, help="What to delete.")
def delete(index: int):
    index -= 1
    if index not in range(len(ssl.cert_db)):
        error(f"Index not within allowed range (1..{len(ssl.cert_db)})")
        return
    entry = ssl.cert_db.pop(index)
    mce(f"§fCertificate entry §d{index + 1}§f deleted (was: §d{entry.subject_cn}§f)§r")


@cloup.command(help="Delete all certificates from the database.")
def clear():
    num = len(ssl.cert_db)
    ssl.cert_db.clear()
    mce(f"§fCertificate database cleared (§d{num}§f entries deleted)§r")


class CommandModule(BaseCommandModule):
    CLI = cli


cli.section("Certificate management", import_, delete, clear)
COMMAND = CommandModule()
