#  Copyright (c) Kuba Szczodrzyński 2026-11-2.

import re
from logging import error, info, warning
from pathlib import Path
from typing import Any, Generator

import click
import cloup
from click import Context
from prettytable.colortable import ColorTable, Themes

from pynetkit.cli.commands.base import (
    CONTEXT_SETTINGS,
    BaseCommandModule,
)
from pynetkit.cli.config import Config
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


@cloup.command(help="Export certificate chain with keys as PEM.")
@cloup.argument(
    "query",
    type=str,
    help="Certificate/CA to export (index, CN or fingerprint).",
)
@cloup.argument(
    "path",
    type=click.Path(writable=True, path_type=Path),
    required=False,
    help="Path to output PEM file (defaults to subject CN).",
)
def export(query: str, path: Path):
    entry = ssl.get_entry(query)
    if not entry:
        error(f"Entry not found by the query: {query}")
        return

    if not path:
        filename = entry.subject_cn.replace("*", "_")
        filename = re.sub(r"[^0-9A-Za-z-_. ]", "", filename)
        path = Path(f"{filename}.pem")
        if path.is_file():
            error(
                f"File {path.absolute().resolve()} already exists, "
                f"please specify a path manually"
            )
            return

    ssl.export_chain(entry=entry, path=path)
    mce(f"§fExported §d{entry.subject_cn}§f as §d{path.absolute().resolve()}§r")

    if not entry.paths:
        entry.paths.add(path)
        ssl.sort_db()
        mce(
            "§fCertificate was auto-generated and is no longer temporary "
            "(will restore with the configuration, once saved)§r"
        )


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


@cloup.command(help="Use a CA or certificate for given host names.")
@cloup.argument(
    "query",
    type=str,
    help="Certificate/CA to assign host names to (index, CN or fingerprint).",
)
@cloup.argument(
    "names",
    type=str,
    nargs=-1,
    required=True,
    help="Domain names (CN) to assign. Wildcard '*' matches one level, '**' matches multiple levels.",
)
@cloup.option(
    "-u",
    "--unuse",
    is_flag=True,
    help="Delete names instead of adding them.",
)
def use(query: str, names: tuple[str], unuse: bool):
    entry = ssl.get_entry(query)
    if not entry:
        error(f"Entry not found by the query: {query}")
        return
    # add or remove names
    if not unuse:
        # run some usage checks
        if "*" in names:
            warning("Domain name '*' matches TLD only; use '**' to match any domain.")
        for name in names:
            if name.startswith("*.") and name.count(".") > 1 and name[2:] not in names:
                info(
                    f"Pattern '{name}' matches subdomain only; "
                    "add separate one without '*.' to match parent domain."
                )
        entry.usage.update(names)
    else:
        entry.usage.difference_update(names)
    mce(
        f"§fEntry §d{entry.subject_cn}§f modified. "
        f"New usage: §d{', '.join(entry.usage) or '(none)'}§r"
    )


@cloup.command(help="Generate a temporary certificate for the given domain name.")
@cloup.argument(
    "names",
    type=str,
    nargs=-1,
    required=True,
    help="Domain name(s); uses SAN if multiple specified. Wildcard '*.' accepted.",
)
def generate(names: tuple[str]):
    for name in names:
        if name.startswith("*.") and name[2:] not in names:
            warning(f"Consider adding wildcard parent ({name[2:]}) to SAN list")
        entry = ssl.find_for_subject(name)
        if entry and entry.key:
            warning(
                f"Certificate for '{name}' already exists: "
                f"{entry.subject_cn}, issued by {entry.issuer_cn}"
            )

    entry = ssl.generate_for_subject(*names)
    if not entry:
        error(f"There is no CA assigned to generate certificates for: {names[0]}")
        return
    mce(
        f"§fGenerated certificate for §d{entry.subject_cn}§f, "
        f"issued by §d{entry.issuer_cn}§r"
    )
    mce(f'§fRun §dssl export "{entry.subject_cn}"§f to make it persist with config§r')


class CommandModule(BaseCommandModule):
    CLI = cli

    def instance_get(self) -> Any:
        return ssl

    def config_get(self) -> Config.Module:
        use_dict: dict[str, list[str]] = {}
        unuse_dict: dict[str, list[str]] = {}
        for entry in ssl.cert_db:
            if not entry.paths:
                continue
            fingerprint = entry.fingerprint.hex()
            defaults = entry.usage_defaults
            use_list = sorted(entry.usage - defaults)
            unuse_list = sorted(defaults - entry.usage)
            if use_list:
                use_dict[fingerprint] = use_list
            if unuse_list:
                unuse_dict[fingerprint] = unuse_list
        return Config.Module(
            order=500,
            config=dict(
                paths=sorted(set(str(p) for e in ssl.cert_db for p in e.paths)),
                use=dict(sorted(use_dict.items())),
                unuse=dict(sorted(unuse_dict.items())),
            ),
            scripts=dict(
                unload=["ssl clear"],
            ),
        )

    def config_commands(self, config: Config.Module) -> Generator[str, None, None]:
        for path in config.config.get("paths", []):
            yield f'ssl import "{path}"'
        for query, names in config.config.get("use", {}).items():
            if not names:
                continue
            yield f'ssl use "{query}" ' + " ".join(f'"{n}"' for n in names)
        for query, names in config.config.get("unuse", {}).items():
            if not names:
                continue
            yield f'ssl use -u "{query}" ' + " ".join(f'"{n}"' for n in names)


cli.section("Certificate management", import_, export, delete, clear)
cli.section("Certificate Authority usage", use, generate)
COMMAND = CommandModule()
