#  Copyright (c) Kuba Szczodrzyński 2024-10-19.

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime
from logging import error, exception, warning
from pathlib import Path

from pynetkit.cli.util.mce import mce
from pynetkit.util.misc import filter_dict, stringify_values
from pynetkit.util.yml import yaml_dump, yaml_load


@dataclass
class Config:
    @dataclass
    class Meta:
        name: str | None = None
        description: str | None = None
        version: str | None = None
        author: str | None = None
        format: int = 1

        def to_mce(self) -> str:
            return f"§9{self.name} §8v{self.version}§r, by §d{self.author}§r"

    @dataclass
    class Module:
        order: int = 1000
        config: dict | list = field(default_factory=dict)
        scripts: dict[str, list[str]] = field(default_factory=dict)

        def __post_init__(self) -> None:
            if self.config:
                self.config = stringify_values(self.config)
            self.scripts = {k: list(filter(None, v)) for k, v in self.scripts.items()}

    @dataclass
    class Script:
        triggers: list[str] = field(default_factory=list)
        commands: list[str] = field(default_factory=list)

    path: Path | None = None
    saved: bool = False

    meta: Meta = field(default_factory=Meta)
    modules: dict[str, Module] = field(default_factory=dict)
    scripts: dict[str, Script] = field(default_factory=dict)

    @staticmethod
    def get() -> "Config":
        return CONFIG

    def get_script(
        self,
        name: str = None,
        *modules: str,
        reverse: bool = False,
    ) -> list[str]:
        commands: list[tuple[int, list[str]]] = []
        if not modules and name in self.scripts:
            commands.append((10000, self.scripts[name].commands))
        for module in filter_dict(dict(self.modules), modules).values():
            if name in module.scripts:
                commands.append((module.order, module.scripts[name]))
        return list(c for k, v in sorted(commands, reverse=reverse) for c in v)

    def update(self) -> None:
        from .command import COMMANDS

        previous = self.saved and self.dump() or None
        found = set()
        for name, (_, module) in sorted(COMMANDS.items()):
            if isinstance(module, str):
                # skip unloaded commands
                continue
            if ".modules." not in type(module).__module__:
                # skip non-module commands
                continue
            found.add(name)
            self.modules[name] = module.config_get()
        not_found = set(self.modules) - found
        for name in not_found:
            warning(f"Module {name} config not found after updating, removing")
            self.modules.pop(name)
        # check if the config has changed
        if previous and previous != self.dump():
            self.saved = False

    def dump(self) -> dict:
        config = dataclasses.asdict(self)
        config.pop("path")
        config.pop("saved")
        return config

    def save(self, path: Path | None, *modules: str) -> None:
        if path:
            self.path = path.resolve()
        if not self.path:
            now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.path = Path(f"pynetkit_{now}.yaml").resolve()
        config = self.dump()
        filter_dict(config["modules"], modules)
        self.path.write_text(yaml_dump(config), encoding="utf-8")
        self.saved = True

    def unload(self, *modules: str) -> None:
        from .command import run_command

        mce("§fRunning §dunload§f script...§r")
        for command in self.get_script("unload", *modules, reverse=True):
            mce(f"§3=> {command}§r")
            run_command(command)

    def reset(self) -> None:
        self.unload()
        mce("§fClearing metadata and all scripts...§r")
        self.meta = Config.Meta()
        self.modules = {}
        self.scripts = {}
        self.path = None
        self.saved = False

    def load(self, path: Path | None, *modules: str) -> None:
        from .command import get_module, run_command

        path = path and path.resolve() or self.path
        if not path:
            error("The config is not loaded from a file; please specify a file to load")
            return

        self.unload(*modules)

        try:
            mce(f"§fParsing config file §d{path}§r")
            config = yaml_load(path.read_text(encoding="utf-8"))
        except Exception as e:
            exception("This is not a valid config file; parse error", exc_info=e)
            return
        try:
            if not modules:
                # entire config is loaded
                self.meta = Config.Meta(**config["meta"])
                self.modules = {
                    k: Config.Module(**v)
                    for k, v in (config.get("modules") or {}).items()
                }
                self.scripts = {
                    k: Config.Script(**v)
                    for k, v in (config.get("scripts") or {}).items()
                }
                self.path = path
                self.saved = True
            else:
                # only certain modules are loaded
                filter_dict(config["modules"], modules)
                self.modules |= {
                    k: Config.Module(**v)
                    for k, v in (config.get("modules") or {}).items()
                }
                self.saved = False
        except Exception as e:
            exception("This is not a valid config file; couldn't load data", exc_info=e)
            return

        mce("§fRunning §dpreload§f script...§r")
        for command in self.get_script("preload", *modules):
            mce(f"§3=> {command}§r")
            run_command(command)

        for name, _ in sorted(config["modules"].items(), key=lambda t: t[1]["order"]):
            mce(f"§fConfiguring module §d{name}§f...§r")
            module = get_module(name)
            if not module:
                return
            for command in module.config_commands(self.modules[name]):
                mce(f"§3=> {command}§r")
                run_command(command)

        mce("§fRunning §dload§f script...§r")
        for command in self.get_script("load", *modules):
            mce(f"§3=> {command}§r")
            run_command(command)


CONFIG = Config()
