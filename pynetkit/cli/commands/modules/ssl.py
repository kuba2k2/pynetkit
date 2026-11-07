#  Copyright (c) Kuba Szczodrzyński 2026-11-2.

import re
from logging import error, info, warning
from pathlib import Path
from typing import Any, Generator

import click
import cloup
from click import Context
from prettytable.colortable import ColorTable, Themes

from pynetkit.cli.command import get_module
from pynetkit.cli.commands.base import (
    CONTEXT_SETTINGS,
    BaseCommandModule,
    async_command,
)
from pynetkit.cli.config import Config
from pynetkit.cli.util.mce import mc, mce
from pynetkit.modules.ssl import SslModule
from pynetkit.util.misc import matches

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
        [" ", "Subject name(s)", "Issuer", "Usage", "Handshakes"],
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

        handshakes = ""
        if not entry.is_ca and entry.fingerprint in ssl.trust_db:
            counts = {True: 0, False: 0}
            total = 0
            for errors in ssl.trust_db[entry.fingerprint].values():
                for e, c in errors.items():
                    counts[not e] += c
                    total += c
            score = f" §3({int(counts[True] / total * 100.0)}%)" if total else ""
            if counts[True] > counts[False]:
                handshakes = f"§2{counts[True]} OK, §8{counts[False]} failed{score}§r"
            elif counts[False] > counts[True]:
                handshakes = f"§8{counts[True]} OK, §c{counts[False]} failed{score}§r"
            else:
                handshakes = f"§3{counts[True]} OK, {counts[False]} failed{score}§r"

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
                mc(handshakes),
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
@async_command
async def import_(paths: tuple[Path]):
    if not ssl.is_started:
        await ssl.start()
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
    help="Path to output PEM file or directory (defaults to subject+issuer CN).",
)
def export(query: str, path: Path):
    entry = ssl.get_entry(query)
    if not entry:
        error(f"Entry not found by the query: {query}")
        return

    if not path or path.is_dir():
        filename = f"{entry.subject_cn} ({entry.issuer_cn})"
        filename = filename.replace("*", "_")
        filename = re.sub(r"[^0-9A-Za-z-_. ()]", "", filename)
        if path:
            path = path / f"{filename}.pem"
        else:
            path = Path(f"{filename}.pem")
        if path.is_file():
            error(
                f"File {path.absolute().resolve()} already exists, "
                f"please specify a path manually"
            )
            return

    with path.open("wb") as f:
        ssl.export_chain(entry=entry, file=f)
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
@cloup.option(
    "-g",
    "--generated",
    is_flag=True,
    help="Only delete auto-generated certificates.",
)
def clear(generated: bool):
    num = len(ssl.cert_db)
    if generated:
        for entry in list(ssl.cert_db):
            if entry.paths:
                continue
            ssl.cert_db.remove(entry)
    else:
        ssl.cert_db.clear()
    mce(
        "§fCertificate database cleared "
        f"(§d{num - len(ssl.cert_db)}§f entries deleted)§r"
    )


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
        if not entry.key:
            error(f"Cannot use {entry.subject_cn} - no private key available")
            return
        if "*" in names:
            warning("Domain name '*' matches TLD only; use '**' to match any domain.")
        for name in names:
            if entry.is_ca and matches(r"(\d+\.){3}\d+", name):
                warning(f"IP address {name} won't be used for certificate generation")
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
        entry = ssl.get_for_subject(name)
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


@cloup.command(help="Enable/disable TLS (pre)master key logging.")
@cloup.argument(
    "path",
    type=click.Path(writable=True, path_type=Path),
    required=False,
    help="Path to output key log file (omit to disable).",
)
def keylog(path: Path | None):
    ssl.keylog_path = path
    if path:
        mce(f"§fTLS key logging is now §aenabled§f (§d{path.resolve()}§f)§r")
    else:
        mce(f"§fTLS key logging is now §4disabled§r")


class CommandModule(BaseCommandModule):
    CLI = cli

    def on_load(self) -> None:
        proxy_module = get_module("proxy", no_import=True)
        if not proxy_module:
            return
        mce("§8Connecting SSL module to all proxies...§r")
        for proxy in proxy_module.instance_get():
            proxy.ssl = ssl

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
                keylog=str(ssl.keylog_path) if ssl.keylog_path else None,
            ),
            scripts=dict(
                unload=["ssl clear"],
            ),
        )

    def config_commands(self, config: Config.Module) -> Generator[str, None, None]:
        paths = config.config.get("paths", [])
        yield f"ssl import " + " ".join(f'"{p}"' for p in paths)
        for query, names in config.config.get("use", {}).items():
            if not names:
                continue
            yield f'ssl use "{query}" ' + " ".join(f'"{n}"' for n in names)
        for query, names in config.config.get("unuse", {}).items():
            if not names:
                continue
            yield f'ssl use -u "{query}" ' + " ".join(f'"{n}"' for n in names)
        keylog = config.config.get("keylog", None)
        if keylog:
            yield f'ssl keylog "{keylog}"'


cli.section("Certificate management", import_, export, delete, clear)
cli.section("Certificate Authority usage", use, generate)
cli.section("SSL MITM configuration", keylog)
COMMAND = CommandModule()
