#  Copyright (c) Kuba Szczodrzyński 2024-10-8.

from abc import ABC

from pynetkit.modules.base import ModuleBase

from .common import WifiCommon

ModuleImpl = None
if ModuleBase.is_windows():
    from .windows import WifiWindows

    ModuleImpl = WifiWindows


class WifiModule(ModuleImpl, WifiCommon, ABC):
    pass
